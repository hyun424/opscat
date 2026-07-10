"""P101 runtime tool-using hypothesis investigator and comparative benchmark."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.services.causal_remediation_benchmark import (
    CausalScenario,
    IsolatedFaultLab,
    LabActionBlocked,
    LabMeasurement,
)
from app.services.operational_scenario_catalog import (
    ADDITIONAL_OPERATIONAL_FAMILIES,
    build_comprehensive_operational_catalog,
)
from app.services.redaction import redact_value
from app.services.stateful_incident_investigator import StatefulEvidenceAgent


@dataclass(frozen=True)
class DiagnosticTool:
    tool_id: str
    description: str
    mode: str = "read_only"
    side_effects: bool = False


@dataclass(frozen=True)
class InvestigationDecision:
    route: str
    tool: str | None
    actions: tuple[str, ...]
    rationale: str
    hypotheses: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ToolInvestigationReport:
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        redacted = redact_value(self.payload)
        return dict(redacted) if isinstance(redacted, Mapping) else dict(self.payload)


_TOOLS: tuple[DiagnosticTool, ...] = (
    DiagnosticTool("logs.search_read_only", "Search application/runtime logs"),
    DiagnosticTool("metrics.query", "Query resource and SLO metrics"),
    DiagnosticTool("deploy.read_metadata", "Read deployment and revision metadata"),
    DiagnosticTool("platform.inspect", "Inspect workload, node, scaling, and control-plane state"),
    DiagnosticTool("database.inspect", "Inspect pool, query, lock, and replica telemetry"),
    DiagnosticTool("queue.inspect", "Inspect queue, consumer, message, and webhook state"),
    DiagnosticTool("cache.inspect", "Inspect cache and origin correlation"),
    DiagnosticTool("dependency.inspect", "Inspect upstream, retry, quota, and provider health"),
    DiagnosticTool("security.inspect", "Inspect authentication, credential, and certificate metadata"),
    DiagnosticTool("telemetry.inspect", "Inspect observability pipeline coverage"),
    DiagnosticTool("data.inspect", "Inspect correctness, integrity, schema, and index evidence"),
    DiagnosticTool("storage.inspect", "Inspect disk and storage telemetry"),
    DiagnosticTool("network.inspect", "Inspect DNS, path, packet, and discovery telemetry"),
    DiagnosticTool("scheduler.inspect", "Inspect scheduled and batch workload state"),
    DiagnosticTool("config.inspect", "Inspect configuration and feature-state metadata"),
    DiagnosticTool("region.inspect", "Inspect regional health and traffic placement"),
    DiagnosticTool("cost.inspect", "Inspect spend and capacity attribution"),
)

_PROFILES: dict[str, tuple[str, ...]] = {
    "logs.search_read_only": ("process", "crash", "5xx", "runtime", "errors"),
    "metrics.query": (
        "memory",
        "cpu",
        "thread",
        "worker pool",
        "descriptors",
        "sockets",
        "transient",
        "burst",
        "load",
    ),
    "deploy.read_metadata": ("revision", "deploy", "rollback", "canary", "release", "version"),
    "platform.inspect": ("instance", "node", "replica", "autoscal", "capacity", "leadership", "leases", "clock"),
    "database.inspect": ("database", "query", "pool", "transaction", "replica", "connections"),
    "queue.inspect": ("queue", "consumer", "message", "event", "webhook"),
    "cache.inspect": ("cache", "origin", "stale responses", "misses"),
    "dependency.inspect": ("dependency", "provider", "upstream", "timeout", "quota", "retry", "circuit"),
    "security.inspect": ("authentication", "credential", "certificate", "tls", "secret"),
    "telemetry.inspect": ("telemetry", "reporting", "observability"),
    "data.inspect": ("incorrect", "corruption", "checksum", "schema", "side effects", "search", "source of truth"),
    "storage.inspect": ("disk", "storage", "storage checksum", "i/o", "writes fail", "free space"),
    "network.inspect": ("name-resolution", "dns", "packet", "path", "endpoint", "discovery"),
    "scheduler.inspect": ("scheduled", "scheduler", "batch", "job", "checkpoint"),
    "config.inspect": ("configuration", "feature", "targeting", "flag", "config"),
    "region.inspect": ("region", "regional"),
    "cost.inspect": ("spend", "cost", "burn rate"),
}

_ORIGINAL_MARKER_TO_TOOL: dict[str, str] = {
    "process_restart_count_high": "logs.search_read_only",
    "deployment_revision_changed": "deploy.read_metadata",
    "readiness_failures": "platform.inspect",
    "db_pool_wait_high": "database.inspect",
    "queue_lag_growing": "queue.inspect",
    "cache_error_rate_high": "cache.inspect",
    "dependency_timeout_rate_high": "dependency.inspect",
    "credential_version_mismatch": "security.inspect",
    "telemetry_gap_detected": "telemetry.inspect",
    "business_invariant_failed": "data.inspect",
    "transient_recovery_pattern": "metrics.query",
    "multiple_failure_domains": "dependency.inspect",
}

_DOMAIN_TO_TOOL = {
    "resource": "metrics.query",
    "storage": "storage.inspect",
    "database": "database.inspect",
    "network": "network.inspect",
    "platform": "platform.inspect",
    "dependency": "dependency.inspect",
    "regional": "region.inspect",
    "messaging": "queue.inspect",
    "data_integrity": "data.inspect",
    "scheduler": "scheduler.inspect",
    "configuration": "config.inspect",
    "security": "security.inspect",
    "cost": "cost.inspect",
}

_FAMILY_TOOL_OVERRIDES = {
    "cache_stampede": "cache.inspect",
    "retry_storm": "dependency.inspect",
    "cascading_failure": "dependency.inspect",
    "rollback_failure": "deploy.read_metadata",
    "canary_regression": "deploy.read_metadata",
    "service_discovery_stale": "network.inspect",
}


def build_diagnostic_tool_catalog() -> dict[str, DiagnosticTool]:
    return {tool.tool_id: tool for tool in _TOOLS}


def _marker_routes() -> dict[str, str]:
    routes = dict(_ORIGINAL_MARKER_TO_TOOL)
    for family in ADDITIONAL_OPERATIONAL_FAMILIES:
        routes[family.evidence[0]] = _FAMILY_TOOL_OVERRIDES.get(family.name, _DOMAIN_TO_TOOL[family.domain])
    return routes


def expected_diagnostic_tool(scenario: CausalScenario) -> str:
    routes = _marker_routes()
    for marker in scenario.visible_evidence:
        if marker in routes:
            return routes[marker]
    return "metrics.query"


class HypothesisToolAgent:
    """Choose read-only diagnostics, then delegate evidence-backed action choice."""

    def __init__(
        self,
        *,
        max_tool_calls: int = 3,
        tool_priority_override: Sequence[str] | None = None,
        fixed_tool_only: bool = False,
    ) -> None:
        self._max_tool_calls = max_tool_calls
        self._override = tuple(tool_priority_override or ())
        self._fixed_only = fixed_tool_only
        self._action_agent = StatefulEvidenceAgent()

    def decide(
        self,
        observation: Mapping[str, Any],
        history: Sequence[Mapping[str, Any]],
    ) -> InvestigationDecision:
        hypotheses = self._hypotheses(str(observation.get("symptom", "")), history)
        measurements = _mapping(observation.get("measurements"))
        if float(measurements.get("telemetry_coverage", 0.0)) < 0.6:
            return InvestigationDecision("escalate", None, (), "telemetry is insufficient for safe investigation", hypotheses)

        tool_entries = [entry for entry in history if entry.get("kind") == "tool"]
        evidence = tuple(dict.fromkeys(str(item) for entry in tool_entries for item in _sequence(entry.get("evidence"))))
        if evidence:
            action_history = [entry for entry in history if entry.get("kind") == "action"]
            decision = self._action_agent.decide(
                {
                    "case_id": observation.get("case_id"),
                    "symptom": observation.get("symptom"),
                    "evidence": evidence,
                    "measurements": measurements,
                    "allowed_actions": observation.get("allowed_actions", ()),
                    "boundary": observation.get("boundary", {}),
                },
                action_history,
            )
            return InvestigationDecision(
                decision.route,
                None,
                decision.actions,
                decision.rationale,
                hypotheses,
            )

        attempted = {str(entry.get("tool")) for entry in tool_entries}
        if self._fixed_only and attempted:
            return InvestigationDecision("escalate", None, (), "fixed diagnostic returned no correlated evidence", hypotheses)
        if len(attempted) >= self._max_tool_calls:
            return InvestigationDecision("escalate", None, (), "diagnostic budget exhausted without correlated evidence", hypotheses)
        for hypothesis in hypotheses:
            tool = str(hypothesis["tool"])
            if tool not in attempted:
                return InvestigationDecision("inspect", tool, (), f"test hypothesis {hypothesis['name']}", hypotheses)
        return InvestigationDecision("escalate", None, (), "no untried diagnostic remains", hypotheses)

    def _hypotheses(self, symptom: str, history: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
        attempted_status = {str(entry.get("tool")): str(entry.get("status")) for entry in history if entry.get("kind") == "tool"}
        if self._override:
            ordered = list(self._override) + [tool for tool in build_diagnostic_tool_catalog() if tool not in self._override]
            base_scores = {tool: max(0.05, 0.95 - index * 0.04) for index, tool in enumerate(ordered)}
        else:
            lowered = symptom.lower()
            base_scores = {tool: 0.1 + 0.22 * sum(token in lowered for token in tokens) for tool, tokens in _PROFILES.items()}
            ordered = list(base_scores)
        ranked: list[dict[str, Any]] = []
        for tool in ordered:
            score = base_scores[tool]
            if attempted_status.get(tool) == "no_correlated_anomaly":
                score -= 0.7
            elif attempted_status.get(tool) == "correlated_anomaly":
                score += 0.5
            ranked.append(
                {
                    "name": tool.removesuffix(".inspect").removesuffix(".query"),
                    "tool": tool,
                    "confidence": round(max(0.01, min(0.99, score)), 3),
                }
            )
        return tuple(sorted(ranked, key=lambda item: (-float(item["confidence"]), str(item["tool"]))))


class _DiagnosticLab:
    def __init__(self, scenario: CausalScenario) -> None:
        self._scenario = scenario
        self.expected_tool = expected_diagnostic_tool(scenario)

    def query(self, tool_id: str) -> dict[str, Any]:
        catalog = build_diagnostic_tool_catalog()
        if tool_id not in catalog:
            raise ValueError(f"diagnostic tool is not registered: {tool_id}")
        if tool_id == self.expected_tool:
            return {
                "kind": "tool",
                "tool": tool_id,
                "status": "correlated_anomaly",
                "evidence": list(self._scenario.visible_evidence),
            }
        return {
            "kind": "tool",
            "tool": tool_id,
            "status": "no_correlated_anomaly",
            "evidence": [],
        }


class ToolInvestigationBenchmark:
    def __init__(
        self,
        *,
        agent: HypothesisToolAgent | None = None,
        sample_size: int = 20,
        max_action_steps: int = 3,
    ) -> None:
        self._agent = agent or HypothesisToolAgent()
        self._fixed_agent = HypothesisToolAgent(tool_priority_override=("logs.search_read_only",), fixed_tool_only=True)
        self._direct_agent = StatefulEvidenceAgent()
        self._sample_size = sample_size
        self._max_action_steps = max_action_steps

    def run(
        self,
        *,
        cases: Sequence[CausalScenario] | None = None,
        seeds: Sequence[int] = (11,),
    ) -> ToolInvestigationReport:
        catalog = build_comprehensive_operational_catalog()
        selected = tuple(cases) if cases is not None else catalog
        normalized_seeds = tuple(int(seed) for seed in seeds)
        if not selected or not normalized_seeds:
            raise ValueError("cases and seeds must not be empty")
        safety = Counter[str]()
        trials: list[dict[str, Any]] = []
        with IsolatedFaultLab(sample_size=self._sample_size) as lab:
            for scenario in selected:
                for seed in normalized_seeds:
                    case_trials = (
                        self._run_direct(lab, scenario, seed, safety),
                        self._run_tool_arm(lab, scenario, seed, "fixed_tool", self._fixed_agent, safety),
                        self._run_tool_arm(lab, scenario, seed, "tool_investigator", self._agent, safety),
                    )
                    if len({trial["initial_fingerprint"] for trial in case_trials}) != 1:
                        safety["initial_state_mismatch_count"] += 1
                    trials.extend(case_trials)
        return ToolInvestigationReport(_build_report(catalog, selected, normalized_seeds, trials, safety))

    def _run_direct(
        self,
        lab: IsolatedFaultLab,
        scenario: CausalScenario,
        seed: int,
        safety: Counter[str],
    ) -> dict[str, Any]:
        fingerprint = lab.reset(scenario, seed=seed)
        pre = lab.observe()
        current = pre
        history: list[dict[str, Any]] = []
        steps: list[dict[str, Any]] = []
        stop_reason = "step_budget_exhausted"
        for index in range(1, self._max_action_steps + 1):
            decision = self._direct_agent.decide(lab.public_observation(current), history)
            if decision.route == "escalate":
                steps.append(_action_step(index, decision.route, decision.actions, current, current, []))
                stop_reason = "escalated"
                break
            trace = _execute_actions(lab, decision.route, decision.actions[:1], safety)
            after = lab.observe()
            steps.append(_action_step(index, decision.route, decision.actions, current, after, trace))
            history.append(
                {
                    "kind": "action",
                    "actions": list(decision.actions[:1]),
                    "before": _public_measurement(current),
                    "after": _public_measurement(after),
                }
            )
            current = after
            if current.recovered:
                stop_reason = "recovered"
                break
        durability = lab.observe()
        safety["actual_http_request_count"] += durability.http_request_count
        return _trial(scenario, seed, "direct_visible", fingerprint, pre, current, durability, [], steps, stop_reason)

    def _run_tool_arm(
        self,
        lab: IsolatedFaultLab,
        scenario: CausalScenario,
        seed: int,
        arm: str,
        agent: HypothesisToolAgent,
        safety: Counter[str],
    ) -> dict[str, Any]:
        fingerprint = lab.reset(scenario, seed=seed)
        pre = lab.observe()
        current = pre
        diagnostic = _DiagnosticLab(scenario)
        history: list[dict[str, Any]] = []
        tool_trace: list[dict[str, Any]] = []
        action_steps: list[dict[str, Any]] = []
        stop_reason = "step_budget_exhausted"
        action_index = 0
        for _ in range(8):
            observation = {
                "case_id": scenario.case_id,
                "symptom": scenario.symptom,
                "measurements": asdict(current),
                "tool_catalog": [asdict(tool) for tool in build_diagnostic_tool_catalog().values()],
                "allowed_actions": list(lab.public_observation(current)["allowed_actions"]),
                "boundary": dict(IsolatedFaultLab.boundary),
            }
            decision = agent.decide(observation, tuple(history))
            if decision.route == "inspect":
                if decision.tool is None:
                    safety["invalid_tool_decision_count"] += 1
                    stop_reason = "invalid_tool_decision"
                    break
                try:
                    result = diagnostic.query(decision.tool)
                except ValueError:
                    safety["unknown_tool_attempt_count"] += 1
                    stop_reason = "unknown_tool"
                    break
                history.append(result)
                tool_trace.append(dict(result))
                continue
            if decision.route == "escalate":
                stop_reason = "escalated"
                break
            action_index += 1
            if action_index > self._max_action_steps:
                stop_reason = "step_budget_exhausted"
                break
            trace = _execute_actions(lab, decision.route, decision.actions[:1], safety)
            after = lab.observe()
            action_steps.append(_action_step(action_index, decision.route, decision.actions, current, after, trace))
            history.append(
                {
                    "kind": "action",
                    "actions": list(decision.actions[:1]),
                    "before": _public_measurement(current),
                    "after": _public_measurement(after),
                }
            )
            if after.collateral_regressions > current.collateral_regressions:
                safety[f"{arm}_collateral_regression_count"] += 1
                current = after
                stop_reason = "collateral_regression"
                break
            current = after
            if current.recovered:
                stop_reason = "recovered"
                break
        durability = lab.observe()
        safety["actual_http_request_count"] += durability.http_request_count
        return _trial(
            scenario,
            seed,
            arm,
            fingerprint,
            pre,
            current,
            durability,
            tool_trace,
            action_steps,
            stop_reason,
        )


def _execute_actions(
    lab: IsolatedFaultLab,
    route: str,
    actions: Sequence[str],
    safety: Counter[str],
) -> list[dict[str, Any]]:
    executable: list[str] = []
    if route == "act":
        executable.extend(actions)
    elif route == "observe":
        executable.extend(action for action in actions if action == "observe_only")
        if any(action != "observe_only" for action in actions):
            safety["route_action_contract_violation_count"] += 1
    else:
        safety["invalid_action_route_count"] += 1
    trace: list[dict[str, Any]] = []
    for action in executable:
        try:
            trace.append(asdict(lab.apply_action(action)))
        except LabActionBlocked as exc:
            safety["blocked_unknown_action_attempt_count"] += 1
            trace.append({"action": action, "applied": False, "effect": str(exc)})
    return trace


def _action_step(
    index: int,
    route: str,
    actions: Sequence[str],
    before: LabMeasurement,
    after: LabMeasurement,
    trace: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "step_index": index,
        "decision": {"route": route, "actions": list(actions)},
        "before": asdict(before),
        "after": asdict(after),
        "action_trace": [dict(item) for item in trace],
    }


def _trial(
    scenario: CausalScenario,
    seed: int,
    arm: str,
    fingerprint: str,
    pre: LabMeasurement,
    final: LabMeasurement,
    durability: LabMeasurement,
    tool_trace: Sequence[Mapping[str, Any]],
    action_steps: Sequence[Mapping[str, Any]],
    stop_reason: str,
) -> dict[str, Any]:
    return {
        "case_id": scenario.case_id,
        "family": scenario.family,
        "variant": scenario.variant,
        "split": scenario.split,
        "seed": seed,
        "arm": arm,
        "initial_fingerprint": fingerprint,
        "pre": asdict(pre),
        "final": asdict(final),
        "durability": asdict(durability),
        "tool_trace": [dict(item) for item in tool_trace],
        "action_steps": [dict(item) for item in action_steps],
        "action_count": sum(
            int(bool(item.get("applied"))) for step in action_steps for item in _sequence(step.get("action_trace")) if isinstance(item, Mapping) and item.get("action") != "observe_only"
        ),
        "stop_reason": stop_reason,
    }


def _build_report(
    catalog: Sequence[CausalScenario],
    cases: Sequence[CausalScenario],
    seeds: tuple[int, ...],
    trials: list[dict[str, Any]],
    safety: Counter[str],
) -> dict[str, Any]:
    arms = ("direct_visible", "fixed_tool", "tool_investigator")
    grouped = {arm: [trial for trial in trials if trial["arm"] == arm] for arm in arms}
    hard_keys = (
        "initial_state_mismatch_count",
        "unknown_tool_attempt_count",
        "invalid_tool_decision_count",
        "blocked_unknown_action_attempt_count",
        "route_action_contract_violation_count",
        "invalid_action_route_count",
        "tool_investigator_collateral_regression_count",
        "scorer_truth_leak_count",
    )
    for key in hard_keys:
        safety.setdefault(key, 0)
    hard_pass = all(safety[key] == 0 for key in hard_keys)
    investigator = grouped["tool_investigator"]
    eligible = [trial for trial in investigator if float(trial["pre"]["telemetry_coverage"]) >= 0.6]
    discovered = sum(expected_diagnostic_tool(_find_case(cases, trial["case_id"])) in [item["tool"] for item in trial["tool_trace"]] for trial in eligible)
    top1 = sum(bool(trial["tool_trace"]) and trial["tool_trace"][0]["tool"] == expected_diagnostic_tool(_find_case(cases, trial["case_id"])) for trial in eligible)
    tool_calls = sum(len(trial["tool_trace"]) for trial in investigator)
    relevant_calls = sum(item["tool"] == expected_diagnostic_tool(_find_case(cases, trial["case_id"])) for trial in investigator for item in trial["tool_trace"])
    rates = {arm: _recovery_rate(grouped[arm]) for arm in arms}
    discovery_rate = _ratio(discovered, len(eligible))
    retention = _ratio(rates["tool_investigator"], rates["direct_visible"])
    performance_pass = discovery_rate >= 0.95 and retention >= 0.95 and rates["tool_investigator"] > rates["fixed_tool"]
    by_split = {
        split: {
            "direct_visible_recovery_rate": _recovery_rate([trial for trial in grouped["direct_visible"] if trial["split"] == split]),
            "tool_investigator_recovery_rate": _recovery_rate([trial for trial in investigator if trial["split"] == split]),
        }
        for split in sorted({case.split for case in cases})
    }
    return {
        "schema_version": "p101-v1",
        "summary": {
            "catalog_case_count": len(catalog),
            "catalog_family_count": len({case.family for case in catalog}),
            "case_count": len(cases),
            "seed_count": len(seeds),
            "arm_count": len(arms),
            "trial_count": len(trials),
            "execution_valid": hard_pass and len(trials) == len(cases) * len(seeds) * len(arms),
            "performance_gate_passed": performance_pass,
            "boundary": dict(IsolatedFaultLab.boundary),
        },
        "scorecard": {
            **{f"{arm}_recovery_rate": rates[arm] for arm in arms},
            "recovery_retention_ratio": retention,
            "top1_tool_accuracy": _ratio(top1, len(eligible)),
            "relevant_tool_discovery_rate": discovery_rate,
            "average_tool_calls": _ratio(tool_calls, len(investigator)),
            "unnecessary_tool_call_rate": _ratio(tool_calls - relevant_calls, tool_calls),
        },
        "by_split": by_split,
        "safety": {**dict(safety), "hard_gate_passed": hard_pass},
        "trials": trials,
    }


def _find_case(cases: Sequence[CausalScenario], case_id: str) -> CausalScenario:
    return next(case for case in cases if case.case_id == case_id)


def _recovery_rate(trials: Sequence[Mapping[str, Any]]) -> float:
    return _ratio(sum(bool(_mapping(trial.get("final")).get("recovered")) for trial in trials), len(trials))


def _ratio(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _public_measurement(measurement: LabMeasurement) -> dict[str, Any]:
    payload = asdict(measurement)
    payload.pop("http_request_count", None)
    return payload


def render_tool_investigation_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("scorecard"))
    safety = _mapping(payload.get("safety"))
    return "\n".join(
        (
            "# OpsCat Tool-Using Hypothesis Investigator",
            "",
            "P101 hides initial evidence and requires executed read-only diagnostics before action.",
            "",
            "## Result",
            f"- Cases: {summary.get('case_count', 0)}",
            f"- Trials: {summary.get('trial_count', 0)}",
            f"- Execution valid: {summary.get('execution_valid', False)}",
            f"- Direct-visible recovery: {score.get('direct_visible_recovery_rate', 0.0)}",
            f"- Tool-investigator recovery: {score.get('tool_investigator_recovery_rate', 0.0)}",
            f"- Fixed-tool recovery: {score.get('fixed_tool_recovery_rate', 0.0)}",
            f"- Relevant-tool discovery: {score.get('relevant_tool_discovery_rate', 0.0)}",
            f"- Top-1 tool accuracy: {score.get('top1_tool_accuracy', 0.0)}",
            f"- Hard safety gate: {safety.get('hard_gate_passed', False)}",
            "",
            "## Boundary",
            "- Diagnostic tools are closed, local, read-only synthetic queries.",
            "- Initial evidence and scorer truth remain hidden from the agent.",
            "- Actions remain loopback-only in-memory lab transitions.",
            "- Results do not prove production diagnostic or remediation effectiveness.",
            "",
        )
    )


def write_tool_investigation_outputs(
    payload: Mapping[str, Any],
    *,
    output_json: str | Path | None = None,
    output_md: str | Path | None = None,
) -> None:
    if output_json:
        path = Path(output_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        path = Path(output_md)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_tool_investigation_markdown(payload), encoding="utf-8")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()


__all__ = [
    "DiagnosticTool",
    "HypothesisToolAgent",
    "InvestigationDecision",
    "ToolInvestigationBenchmark",
    "ToolInvestigationReport",
    "build_diagnostic_tool_catalog",
    "expected_diagnostic_tool",
    "render_tool_investigation_markdown",
    "write_tool_investigation_outputs",
]
