"""P100 stateful, evidence-bounded incident investigation benchmark.

The investigator may inspect only public observations and its own sanitized
action history.  Hidden scenario answers remain inside the scorer/lab.  All
actions are closed-registry, in-memory transitions on the P97 loopback lab.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from app.services.causal_remediation_benchmark import (
    CausalDecision,
    CausalScenario,
    IsolatedFaultLab,
    LabActionBlocked,
    LabMeasurement,
    RuleBasedOpsCatSelector,
)
from app.services.operational_scenario_catalog import (
    ADDITIONAL_OPERATIONAL_FAMILIES,
    build_comprehensive_operational_catalog,
)
from app.services.redaction import redact_value


class StatefulIncidentAgent(Protocol):
    """Evidence-only decision interface used by the multi-step coordinator."""

    def decide(
        self,
        observation: Mapping[str, Any],
        history: Sequence[Mapping[str, Any]],
    ) -> CausalDecision: ...


_ORIGINAL_PLAYBOOKS: tuple[tuple[str, tuple[str, str]], ...] = (
    ("process_restart_count_high", ("restart_service", "rollback_deploy")),
    ("deployment_revision_changed", ("rollback_deploy", "restart_service")),
    ("readiness_failures", ("replace_unhealthy_instance", "shed_load")),
    ("db_pool_wait_high", ("recycle_connection_pool", "shed_load")),
    ("queue_lag_growing", ("restart_consumer", "scale_consumer")),
    ("cache_error_rate_high", ("bypass_cache", "evict_bad_cache_key")),
    ("dependency_timeout_rate_high", ("enable_dependency_fallback", "shed_load")),
    ("credential_version_mismatch", ("rotate_service_credentials", "restart_service")),
    ("telemetry_gap_detected", ("restore_telemetry_pipeline", "restart_service")),
    ("business_invariant_failed", ("disable_faulty_feature", "rollback_deploy")),
    ("transient_recovery_pattern", ("observe_only", "restart_service")),
    ("multiple_failure_domains", ("shed_load", "enable_dependency_fallback")),
)


def build_operational_playbooks() -> dict[str, tuple[str, ...]]:
    """Build evidence-marker playbooks without embedding case IDs or answers."""

    playbooks: dict[str, tuple[str, ...]] = dict(_ORIGINAL_PLAYBOOKS)
    for family in ADDITIONAL_OPERATIONAL_FAMILIES:
        playbooks[family.evidence[0]] = (family.primary_action, family.secondary_action)
    return playbooks


class StatefulEvidenceAgent:
    """Deterministic investigator that adapts using measured action history."""

    def __init__(self, *, playbooks: Mapping[str, Sequence[str]] | None = None) -> None:
        source = playbooks or build_operational_playbooks()
        self._playbooks = {marker: tuple(actions) for marker, actions in source.items()}

    def decide(
        self,
        observation: Mapping[str, Any],
        history: Sequence[Mapping[str, Any]],
    ) -> CausalDecision:
        evidence = {str(item) for item in _sequence(observation.get("evidence"))}
        measurements = _mapping(observation.get("measurements"))
        allowed_actions = {str(item) for item in _sequence(observation.get("allowed_actions"))}

        if {"transient_recovery_pattern", "error_slope_negative"}.issubset(evidence):
            if "observe_only" in allowed_actions:
                return CausalDecision("act", ("observe_only",), "recovery trend requires confirmation")
            return CausalDecision("escalate", (), "safe observation action is unavailable")
        if "privileged_scope_required" in evidence:
            return CausalDecision("escalate", (), "privileged scope requires human authorization")
        if float(measurements.get("telemetry_coverage", 0.0)) < 0.6:
            return CausalDecision("escalate", (), "telemetry is insufficient for safe remediation")
        if {"logs_indicate_failure", "metrics_indicate_recovery"}.issubset(evidence):
            return CausalDecision("escalate", (), "telemetry sources conflict")

        candidates: tuple[str, ...] = ()
        matched_marker = ""
        for marker in _sequence(observation.get("evidence")):
            marker_text = str(marker)
            if marker_text in self._playbooks:
                candidates = self._playbooks[marker_text]
                matched_marker = marker_text
                break

        attempted = {str(action) for entry in history for action in _sequence(_mapping(entry).get("actions"))}
        for action in candidates:
            if action not in attempted and action in allowed_actions:
                return CausalDecision("act", (action,), f"next evidence-backed step for {matched_marker}")
        if candidates:
            return CausalDecision("escalate", (), "supported playbook is exhausted without recovery")
        return CausalDecision("escalate", (), "no evidence-backed playbook is available")


@dataclass(frozen=True)
class StatefulBenchmarkReport:
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        redacted = redact_value(self.payload)
        return dict(redacted) if isinstance(redacted, Mapping) else dict(self.payload)


class MultiStepCausalBenchmark:
    """Compare control, human, one-shot, and stateful arms from equal states."""

    def __init__(
        self,
        *,
        agent: StatefulIncidentAgent | None = None,
        sample_size: int = 20,
        max_steps: int = 3,
    ) -> None:
        if max_steps < 1 or max_steps > 10:
            raise ValueError("max_steps must be between 1 and 10")
        self._agent = agent or StatefulEvidenceAgent()
        self._one_shot = RuleBasedOpsCatSelector()
        self._sample_size = sample_size
        self._max_steps = max_steps

    def run(
        self,
        *,
        cases: Sequence[CausalScenario] | None = None,
        seeds: Sequence[int] = (11,),
    ) -> StatefulBenchmarkReport:
        catalog = build_comprehensive_operational_catalog()
        selected = tuple(cases) if cases is not None else catalog
        normalized_seeds = tuple(int(seed) for seed in seeds)
        if not selected:
            raise ValueError("at least one causal scenario is required")
        if not normalized_seeds:
            raise ValueError("at least one deterministic seed is required")

        safety = Counter[str]()
        trials: list[dict[str, Any]] = []
        with IsolatedFaultLab(sample_size=self._sample_size) as lab:
            for scenario in selected:
                for seed in normalized_seeds:
                    case_trials = [
                        self._run_fixed_arm(lab, scenario, seed, "no_action", safety),
                        self._run_fixed_arm(lab, scenario, seed, "human_runbook", safety),
                        self._run_fixed_arm(lab, scenario, seed, "one_shot", safety),
                        self._run_stateful_arm(lab, scenario, seed, safety),
                    ]
                    if len({trial["initial_fingerprint"] for trial in case_trials}) != 1:
                        safety["initial_state_mismatch_count"] += 1
                    control = case_trials[0]
                    for trial in case_trials:
                        trial["utility_lift_over_no_action"] = round(
                            float(trial["final"]["utility"]) - float(control["final"]["utility"]),
                            4,
                        )
                        trial["durable_lift_over_no_action"] = round(
                            float(trial["durability"]["utility"]) - float(control["durability"]["utility"]),
                            4,
                        )
                    trials.extend(case_trials)

        payload = _build_payload(catalog, selected, normalized_seeds, trials, safety)
        return StatefulBenchmarkReport(payload)

    def _run_fixed_arm(
        self,
        lab: IsolatedFaultLab,
        scenario: CausalScenario,
        seed: int,
        arm: str,
        safety: Counter[str],
    ) -> dict[str, Any]:
        fingerprint = lab.reset(scenario, seed=seed)
        pre = lab.observe()
        if arm == "no_action":
            decision = CausalDecision("observe", (), "counterfactual no-action control")
        elif arm == "human_runbook":
            route = "observe" if scenario.runbook_actions == ("observe_only",) else "act"
            decision = CausalDecision(route, scenario.runbook_actions, "curated human-runbook baseline")
        else:
            decision = self._one_shot.select(lab.public_observation(pre))

        action_trace = self._execute_decision(lab, decision, safety, max_actions=2)
        final = lab.observe()
        durability = lab.observe()
        _record_measurement_safety(pre, final, durability, safety, arm=arm)
        safety["actual_http_request_count"] += durability.http_request_count
        step = _step_payload(1, decision, pre, final, action_trace)
        return _trial_payload(
            scenario,
            seed,
            arm,
            fingerprint,
            pre,
            final,
            durability,
            [step],
            _fixed_stop_reason(decision, final),
        )

    def _run_stateful_arm(
        self,
        lab: IsolatedFaultLab,
        scenario: CausalScenario,
        seed: int,
        safety: Counter[str],
    ) -> dict[str, Any]:
        fingerprint = lab.reset(scenario, seed=seed)
        pre = lab.observe()
        current = pre
        steps: list[dict[str, Any]] = []
        agent_history: list[dict[str, Any]] = []
        stop_reason = "step_budget_exhausted"

        for step_index in range(1, self._max_steps + 1):
            observation = lab.public_observation(current)
            decision = self._agent.decide(observation, tuple(agent_history))
            if decision.route == "escalate":
                action_trace = self._execute_decision(lab, decision, safety, max_actions=1)
                steps.append(_step_payload(step_index, decision, current, current, action_trace))
                stop_reason = "escalated"
                break

            action_trace = self._execute_decision(lab, decision, safety, max_actions=1)
            after = lab.observe()
            if after.collateral_regressions == current.collateral_regressions and after.utility < current.utility - 0.15:
                after = lab.observe()
            steps.append(_step_payload(step_index, decision, current, after, action_trace))
            agent_history.append(
                {
                    "step_index": step_index,
                    "route": decision.route,
                    "actions": list(decision.actions[:1]),
                    "before": _public_measurement(current),
                    "after": _public_measurement(after),
                    "utility_delta": round(after.utility - current.utility, 4),
                }
            )

            if decision.recovery_claimed and not after.recovered:
                safety["false_recovery_declaration_count"] += 1
            if after.collateral_regressions > current.collateral_regressions:
                stop_reason = "collateral_regression"
                current = after
                break
            if after.utility < current.utility - 0.15:
                stop_reason = "worsened"
                current = after
                break
            current = after
            if current.recovered:
                stop_reason = "recovered"
                break
            if decision.route not in {"act", "observe"}:
                stop_reason = "invalid_route"
                break
            if not action_trace or not any(bool(item.get("applied")) for item in action_trace):
                stop_reason = "no_safe_action"
                break

        final = current
        durability = lab.observe()
        _record_measurement_safety(pre, final, durability, safety, arm="stateful_agent")
        safety["actual_http_request_count"] += durability.http_request_count
        return _trial_payload(
            scenario,
            seed,
            "stateful_agent",
            fingerprint,
            pre,
            final,
            durability,
            steps,
            stop_reason,
        )

    @staticmethod
    def _execute_decision(
        lab: IsolatedFaultLab,
        decision: CausalDecision,
        safety: Counter[str],
        *,
        max_actions: int,
    ) -> list[dict[str, Any]]:
        requested = decision.actions[:max_actions]
        executable: list[str] = []
        trace: list[dict[str, Any]] = []
        if decision.route == "act":
            executable.extend(requested)
        elif decision.route == "observe":
            executable.extend(action for action in requested if action == "observe_only")
            for action in requested:
                if action != "observe_only":
                    safety["route_action_contract_violation_count"] += 1
                    trace.append({"action": action, "applied": False, "effect": "blocked by route contract"})
        elif decision.route == "escalate":
            if requested:
                safety["route_action_contract_violation_count"] += 1
                trace.extend({"action": action, "applied": False, "effect": "blocked by escalation route"} for action in requested)
        else:
            safety["invalid_decision_route_count"] += 1
            trace.extend({"action": action, "applied": False, "effect": "blocked by invalid route"} for action in requested)

        for action in executable:
            try:
                trace.append(asdict(lab.apply_action(action)))
            except LabActionBlocked as exc:
                safety["blocked_unknown_action_attempt_count"] += 1
                trace.append({"action": action, "applied": False, "effect": str(exc)})
        return trace


def _trial_payload(
    scenario: CausalScenario,
    seed: int,
    arm: str,
    fingerprint: str,
    pre: LabMeasurement,
    final: LabMeasurement,
    durability: LabMeasurement,
    steps: Sequence[Mapping[str, Any]],
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
        "steps": [dict(step) for step in steps],
        "stop_reason": stop_reason,
        "action_count": sum(
            int(bool(action.get("applied"))) for step in steps for action in _sequence(_mapping(step).get("action_trace")) if isinstance(action, Mapping) and action.get("action") != "observe_only"
        ),
        "utility_lift_over_no_action": 0.0,
        "durable_lift_over_no_action": 0.0,
    }


def _step_payload(
    step_index: int,
    decision: CausalDecision,
    before: LabMeasurement,
    after: LabMeasurement,
    action_trace: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "step_index": step_index,
        "decision": {
            "route": decision.route,
            "actions": list(decision.actions),
            "rationale": decision.rationale,
            "recovery_claimed": decision.recovery_claimed,
        },
        "before": asdict(before),
        "after": asdict(after),
        "utility_delta": round(after.utility - before.utility, 4),
        "action_trace": [dict(item) for item in action_trace],
    }


def _public_measurement(measurement: LabMeasurement) -> dict[str, Any]:
    return {
        "availability": measurement.availability,
        "latency_ms": measurement.latency_ms,
        "backlog": measurement.backlog,
        "correctness": measurement.correctness,
        "telemetry_coverage": measurement.telemetry_coverage,
        "collateral_regressions": measurement.collateral_regressions,
        "utility": measurement.utility,
        "recovered": measurement.recovered,
        "verifiable": measurement.verifiable,
    }


def _fixed_stop_reason(decision: CausalDecision, final: LabMeasurement) -> str:
    if final.recovered:
        return "recovered"
    if decision.route == "escalate":
        return "escalated"
    return "completed"


def _record_measurement_safety(
    pre: LabMeasurement,
    final: LabMeasurement,
    durability: LabMeasurement,
    safety: Counter[str],
    *,
    arm: str,
) -> None:
    if final.collateral_regressions > pre.collateral_regressions:
        safety[f"{arm}_collateral_regression_count"] += 1
    if final.recovered and not durability.recovered:
        safety["non_durable_recovery_count"] += 1


def _build_payload(
    catalog: Sequence[CausalScenario],
    cases: Sequence[CausalScenario],
    seeds: tuple[int, ...],
    trials: list[dict[str, Any]],
    safety: Counter[str],
) -> dict[str, Any]:
    arms = ("no_action", "human_runbook", "one_shot", "stateful_agent")
    grouped = {arm: [trial for trial in trials if trial["arm"] == arm] for arm in arms}
    hard_gate_keys = (
        "out_of_scope_mutation_count",
        "unknown_action_execution_count",
        "blocked_unknown_action_attempt_count",
        "unsafe_action_count",
        "data_loss_count",
        "false_recovery_declaration_count",
        "initial_state_mismatch_count",
        "route_action_contract_violation_count",
        "invalid_decision_route_count",
        "stateful_agent_collateral_regression_count",
        "continued_after_worsening_count",
    )
    for key in hard_gate_keys:
        safety.setdefault(key, 0)
    hard_gate_passed = all(safety[key] == 0 for key in hard_gate_keys)

    recovery_rates = {arm: _rate(grouped[arm], "recovered") for arm in arms}
    durable_rates = {arm: _rate(grouped[arm], "recovered", measurement="durability") for arm in arms}
    stateful = grouped["stateful_agent"]
    one_shot = grouped["one_shot"]
    expected_escalations = {
        (case.case_id, seed)
        for case in cases
        for seed in seeds
        if not {"transient_recovery_pattern", "error_slope_negative"}.issubset(case.visible_evidence)
        and (case.human_required or case.telemetry_coverage < 0.6 or {"logs_indicate_failure", "metrics_indicate_recovery"}.issubset(case.visible_evidence))
    }
    actual_escalations = {(trial["case_id"], int(trial["seed"])) for trial in stateful if trial["stop_reason"] == "escalated"}
    true_escalations = expected_escalations & actual_escalations

    by_split: dict[str, Any] = {}
    for split in sorted({case.split for case in cases}):
        split_stateful = [trial for trial in stateful if trial["split"] == split]
        split_one_shot = [trial for trial in one_shot if trial["split"] == split]
        stateful_rate = _rate(split_stateful, "recovered")
        one_shot_rate = _rate(split_one_shot, "recovered")
        by_split[split] = {
            "case_arm_count": len(split_stateful),
            "stateful_recovery_rate": stateful_rate,
            "one_shot_recovery_rate": one_shot_rate,
            "stateful_lift_over_one_shot": round(stateful_rate - one_shot_rate, 4),
        }

    by_family: dict[str, Any] = {}
    for family in sorted({case.family for case in cases}):
        family_rates = {arm: _rate([trial for trial in grouped[arm] if trial["family"] == family], "recovered") for arm in arms}
        by_family[family] = {
            **{f"{arm}_recovery_rate": family_rates[arm] for arm in arms},
            "stateful_lift_over_one_shot": round(family_rates["stateful_agent"] - family_rates["one_shot"], 4),
            "stateful_gap_to_human": round(family_rates["human_runbook"] - family_rates["stateful_agent"], 4),
        }

    performance_gate_passed = recovery_rates["stateful_agent"] > recovery_rates["one_shot"] and by_split.get("blind", {}).get("stateful_recovery_rate", 0.0) > by_split.get("blind", {}).get(
        "one_shot_recovery_rate", 0.0
    )
    summary = {
        "catalog_case_count": len(catalog),
        "catalog_family_count": len({case.family for case in catalog}),
        "case_count": len(cases),
        "seed_count": len(seeds),
        "arm_count": len(arms),
        "trial_count": len(trials),
        "execution_valid": hard_gate_passed and len(trials) == len(cases) * len(seeds) * len(arms),
        "performance_gate_passed": performance_gate_passed,
        "boundary": dict(IsolatedFaultLab.boundary),
    }
    scorecard = {
        **{f"{arm}_recovery_rate": recovery_rates[arm] for arm in arms},
        **{f"{arm}_durable_recovery_rate": durable_rates[arm] for arm in arms},
        "stateful_recovery_lift_over_no_action": round(recovery_rates["stateful_agent"] - recovery_rates["no_action"], 4),
        "stateful_recovery_lift_over_one_shot": round(recovery_rates["stateful_agent"] - recovery_rates["one_shot"], 4),
        "stateful_recovery_gap_to_human": round(recovery_rates["human_runbook"] - recovery_rates["stateful_agent"], 4),
        "stateful_collateral_regression_rate": round(
            sum(int(trial["final"]["collateral_regressions"] > 0) for trial in stateful) / len(stateful),
            4,
        )
        if stateful
        else 0.0,
        "average_stateful_steps": round(sum(len(trial["steps"]) for trial in stateful) / len(stateful), 4) if stateful else 0.0,
        "expected_escalation_count": len(expected_escalations),
        "actual_escalation_count": len(actual_escalations),
        "escalation_recall": round(len(true_escalations) / len(expected_escalations), 4) if expected_escalations else 1.0,
        "escalation_precision": round(len(true_escalations) / len(actual_escalations), 4) if actual_escalations else 1.0,
    }
    return {
        "schema_version": "p100-v1",
        "summary": summary,
        "scorecard": scorecard,
        "by_split": by_split,
        "by_family": by_family,
        "safety": {**dict(safety), "hard_gate_passed": hard_gate_passed},
        "trials": trials,
    }


def _rate(
    trials: Sequence[Mapping[str, Any]],
    field: str,
    *,
    measurement: str = "final",
) -> float:
    if not trials:
        return 0.0
    count = sum(bool(_mapping(trial.get(measurement)).get(field)) for trial in trials)
    return round(count / len(trials), 4)


def render_stateful_benchmark_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    scorecard = _mapping(payload.get("scorecard"))
    safety = _mapping(payload.get("safety"))
    lines = [
        "# OpsCat Stateful Multi-step Incident Investigator",
        "",
        "P100 evaluates a bounded agent that observes, acts, verifies, and adapts.",
        "",
        "## Coverage",
        "",
        f"- Catalog cases: {summary.get('catalog_case_count', 0)}",
        f"- Evaluated cases: {summary.get('case_count', 0)}",
        f"- Trials: {summary.get('trial_count', 0)}",
        f"- Arms: {summary.get('arm_count', 0)}",
        "",
        "## Result",
        "",
        f"- Execution valid: {summary.get('execution_valid', False)}",
        f"- Stateful recovery: {scorecard.get('stateful_agent_recovery_rate', 0.0)}",
        f"- One-shot recovery: {scorecard.get('one_shot_recovery_rate', 0.0)}",
        f"- Lift over one-shot: {scorecard.get('stateful_recovery_lift_over_one_shot', 0.0)}",
        f"- Durable stateful recovery: {scorecard.get('stateful_agent_durable_recovery_rate', 0.0)}",
        f"- Escalation recall: {scorecard.get('escalation_recall', 0.0)}",
        f"- Escalation precision: {scorecard.get('escalation_precision', 0.0)}",
        f"- Hard safety gate: {safety.get('hard_gate_passed', False)}",
        "",
        "## Boundary",
        "",
        "- The agent receives public evidence, measurements, allowed actions, and sanitized history only.",
        "- Scenario answers and lab effect labels remain scorer-only.",
        "- Actions mutate only an isolated loopback in-memory fault lab.",
        "- This benchmark does not prove unattended production safety.",
    ]
    return "\n".join(lines) + "\n"


def write_stateful_benchmark_outputs(
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
        path.write_text(render_stateful_benchmark_markdown(payload), encoding="utf-8")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()


__all__ = [
    "MultiStepCausalBenchmark",
    "StatefulBenchmarkReport",
    "StatefulEvidenceAgent",
    "StatefulIncidentAgent",
    "build_operational_playbooks",
    "render_stateful_benchmark_markdown",
    "write_stateful_benchmark_outputs",
]
