"""P104 evidence-gap sufficiency investigator.

This module is intentionally local and deterministic. It reuses the P101
read-only diagnostic catalog, keeps provider output advisory, and only exposes a
P100-compatible handoff when hard evidence sufficiency gates pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.services.redaction import redact_value
from app.services.tool_using_hypothesis_investigator import build_diagnostic_tool_catalog

SCHEMA_VERSION = "p104.evidence_gap.decision.v1"
ALLOWED_ROUTES = frozenset({"inspect_next", "sufficient_for_policy_handoff", "escalate_gap", "abstain_fail_closed"})
EVIDENCE_STATES = frozenset({"supporting", "contradicting", "absent", "stale", "unavailable", "distracting", "duplicate", "not_yet_queried"})
CRITICALITIES = frozenset({"critical", "optional", "contradiction_check"})
SCORER_ONLY_KEYS = frozenset({"family", "variant", "split", "expected_tool", "expected_sufficiency", "required_action", "harmful_action", "runbook_answer", "outcome_label", "hidden_scorer_truth"})
BOUNDARY = {"read_only_tools_only": True, "production_mutation_enabled": False, "action_authority": False}
SEED_PATH = Path("evals/evidence_gap/seed/scenarios.json")

_SECRET_OR_INSTRUCTION_RE = re.compile(
    r"(AWS_SECRET_ACCESS_KEY=)[^\s,;]+|(curl\s+https?://[^\s,;]+)|(route=sufficient_for_policy_handoff)",
    re.IGNORECASE,
)


class EvidenceGapProvider(Protocol):
    name: str
    model_calls_enabled: bool

    def complete(self, messages: list[dict[str, str]]) -> Mapping[str, Any] | str: ...


@dataclass(frozen=True)
class EvidenceGapBudget:
    max_tool_calls: int = 3
    max_provider_calls: int = 0
    max_steps: int = 5
    wall_clock_seconds: int = 30
    allow_exhausted: bool = False

    def __post_init__(self) -> None:
        if self.allow_exhausted:
            if min(self.max_tool_calls, self.max_provider_calls, self.max_steps, self.wall_clock_seconds) < 0:
                raise ValueError("budget bounds cannot be negative")
            if self.wall_clock_seconds < 1:
                raise ValueError("wall_clock_seconds must be positive")
            return
        if self.max_tool_calls < 1:
            raise ValueError("max_tool_calls must be positive")
        if self.max_provider_calls < 0:
            raise ValueError("max_provider_calls cannot be negative")
        if self.max_steps < 1:
            raise ValueError("max_steps must be positive")
        if self.wall_clock_seconds < 1:
            raise ValueError("wall_clock_seconds must be positive")


@dataclass(frozen=True)
class EvidenceGapBenchmarkReport:
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload)


class RateMetric(dict[str, Any]):
    def __lt__(self, other: Any) -> bool:
        return self._rate() < _metric_rate(other)

    def __le__(self, other: Any) -> bool:
        return self._rate() <= _metric_rate(other)

    def __gt__(self, other: Any) -> bool:
        return self._rate() > _metric_rate(other)

    def __ge__(self, other: Any) -> bool:
        return self._rate() >= _metric_rate(other)

    def __float__(self) -> float:
        return self._rate()

    def _rate(self) -> float:
        return float(self.get("rate", 0.0))


def validate_decision_envelope(envelope: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(envelope)
    for key in ("episode_id", "decision_id", "schema_version", "hypothesis_id", "requirement_set_id", "route"):
        if not str(item.get(key, "")):
            raise ValueError(f"{key} is required")
    if item["route"] not in ALLOWED_ROUTES:
        raise ValueError("unknown evidence-gap route")
    seen_evidence: set[str] = set()
    for record in _sequence(item.get("evidence_states")):
        evidence = _mapping(record)
        evidence_id = str(evidence.get("evidence_id", ""))
        if not evidence_id or evidence_id in seen_evidence:
            raise ValueError("evidence IDs must be present and unique")
        seen_evidence.add(evidence_id)
        if evidence.get("state") not in EVIDENCE_STATES:
            raise ValueError("unknown evidence state")
    budgets = _mapping(item.get("budget_counters"))
    for key in ("remaining_tool_budget", "remaining_provider_budget", "elapsed_step_count", "provider_model_call_count"):
        if int(budgets.get(key, 0)) < 0:
            raise ValueError("budget counters cannot be negative")
    if item["route"] == "sufficient_for_policy_handoff":
        _validate_sufficient_envelope(item)
    item["boundary"] = dict(BOUNDARY)
    return item


def serialize_decision_envelope(envelope: Mapping[str, Any]) -> str:
    return json.dumps(validate_decision_envelope(envelope), sort_keys=True, separators=(",", ":"))


def to_public_provider_packet(envelope: Mapping[str, Any]) -> dict[str, Any]:
    public = _strip_scorer(envelope)
    packet = {
        "schema_version": public.get("schema_version"),
        "episode_id": public.get("episode_id"),
        "decision_id": public.get("decision_id"),
        "hypothesis_id": public.get("hypothesis_id"),
        "requirement_set_id": public.get("requirement_set_id"),
        "route": public.get("route"),
        "public_observation": public.get("public_observation", {}),
        "requirements": public.get("requirements", []),
        "evidence_states": public.get("evidence_states", []),
        "closed_catalog": list(build_diagnostic_tool_catalog()),
        "attempted_tools": public.get("attempted_tools", []),
        "remaining_tool_budget": _mapping(public.get("budget_counters")).get("remaining_tool_budget", 0),
        "remaining_provider_budget": _mapping(public.get("budget_counters")).get("remaining_provider_budget", 0),
        "trace_ids": public.get("trace_ids", []),
        "boundary": dict(BOUNDARY),
    }
    return _provider_key_safe(_sanitize_public(packet))


def adapt_to_p100_policy_handoff(envelope: Mapping[str, Any]) -> dict[str, Any]:
    item = validate_decision_envelope(envelope)
    if item["route"] != "sufficient_for_policy_handoff":
        raise ValueError("P100 policy handoff requires sufficient evidence")
    _validate_sufficient_envelope(item)
    return {
        "route": "policy_handoff",
        "hypothesis_id": item["hypothesis_id"],
        "requirement_set_id": item["requirement_set_id"],
        "citation_evidence_ids": list(_sequence(_mapping(item.get("sufficiency_decision")).get("citation_evidence_ids"))),
        "boundary": dict(BOUNDARY),
    }


def validate_evidence_requirement(requirement: Mapping[str, Any], catalog: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(requirement)
    for key in ("requirement_id", "source_family", "candidate_tools", "criticality", "accepted_states", "freshness_seconds", "contradiction_policy", "rationale"):
        if key not in item:
            raise ValueError(f"{key} is required")
    if item["criticality"] not in CRITICALITIES:
        raise ValueError("unknown criticality")
    if item["criticality"] == "optional" and bool(item.get("required")):
        raise ValueError("optional requirement cannot be marked required")
    if not set(str(tool) for tool in _sequence(item.get("candidate_tools"))) <= set(catalog):
        raise ValueError("requirement names an unsupported diagnostic tool")
    if not set(str(state) for state in _sequence(item.get("accepted_states"))) <= EVIDENCE_STATES:
        raise ValueError("requirement names an unsupported evidence state")
    if int(item.get("freshness_seconds", 0)) < 1:
        raise ValueError("freshness_seconds must be positive")
    _reject_scorer_text(item.get("rationale", ""))
    return item


def validate_requirement_set(requirements: Sequence[Mapping[str, Any]], catalog: Mapping[str, Any], *, action_ready: bool = False) -> dict[str, Any]:
    validated = [validate_evidence_requirement(requirement, catalog) for requirement in requirements]
    if action_ready:
        if not any(item["criticality"] == "critical" for item in validated):
            raise ValueError("action-ready requirement set needs critical evidence")
        if not any(item["criticality"] == "contradiction_check" for item in validated):
            raise ValueError("action-ready requirement set needs a contradiction check")
    return {"action_ready": action_ready, "requirements": validated}


def classify_requirement_state(requirement: Mapping[str, Any], records: Sequence[Mapping[str, Any]], *, now_tick: int) -> dict[str, Any]:
    req_id = str(requirement.get("requirement_id"))
    accepted = {str(state) for state in _sequence(requirement.get("accepted_states"))}
    matching = [_mapping(record) for record in records if req_id in {str(item) for item in _sequence(_mapping(record).get("requirement_ids"))}]
    result: dict[str, Any] = {
        "requirement_id": req_id,
        "satisfying_evidence_ids": [],
        "contradicting_evidence_ids": [],
        "absent_evidence_ids": [],
        "stale_evidence_ids": [],
        "unavailable_evidence_ids": [],
        "duplicate_evidence_ids": [],
        "distracting_evidence_ids": [],
        "valid_absence_count": 0,
        "unavailable_count": 0,
    }
    for record in matching:
        state = str(record.get("state"))
        evidence_id = str(record.get("evidence_id"))
        if state == "contradicting":
            result["contradicting_evidence_ids"].append(evidence_id)
        elif state == "absent":
            result["absent_evidence_ids"].append(evidence_id)
            result["valid_absence_count"] += 1
            if state in accepted:
                result["satisfying_evidence_ids"].append(evidence_id)
        elif state == "stale" or _is_too_old(requirement, record, now_tick):
            result["stale_evidence_ids"].append(evidence_id)
        elif state == "unavailable":
            result["unavailable_evidence_ids"].append(evidence_id)
            result["unavailable_count"] += 1
        elif state == "duplicate":
            result["duplicate_evidence_ids"].append(evidence_id)
        elif state == "distracting":
            result["distracting_evidence_ids"].append(evidence_id)
        elif state in accepted:
            result["satisfying_evidence_ids"].append(evidence_id)
    return result


def decide_evidence_sufficiency(
    *,
    hypothesis_id: str,
    requirement_set_id: str,
    requirements: Sequence[Mapping[str, Any]],
    evidence_states: Sequence[Mapping[str, Any]],
    telemetry_coverage: float,
    now_tick: int,
) -> dict[str, Any]:
    catalog = build_diagnostic_tool_catalog()
    validated = list(validate_requirement_set(requirements, catalog, action_ready=True)["requirements"])
    states = [dict(_mapping(record)) for record in evidence_states]
    critical = [item for item in validated if item["criticality"] in {"critical", "contradiction_check"}]
    classified = [classify_requirement_state(item, states, now_tick=now_tick) for item in critical]
    missing: list[str] = []
    stale: list[str] = []
    unavailable: list[str] = []
    contradiction_ids: list[str] = []
    citations: list[str] = []
    satisfied: list[str] = []
    for requirement, status in zip(critical, classified, strict=True):
        req_id = str(requirement["requirement_id"])
        if status["contradicting_evidence_ids"]:
            contradiction_ids.extend(status["contradicting_evidence_ids"])
        if status["unavailable_evidence_ids"]:
            unavailable.append(req_id)
        if status["stale_evidence_ids"]:
            stale.append(req_id)
        if status["satisfying_evidence_ids"]:
            satisfied.append(req_id)
            citations.extend(str(item) for item in status["satisfying_evidence_ids"])
        else:
            missing.append(req_id)
    hard_gaps: list[str] = []
    if telemetry_coverage < 0.6:
        hard_gaps.append("low_coverage")
    if missing:
        hard_gaps.append("missing")
    if stale:
        hard_gaps.append("stale")
    if unavailable:
        hard_gaps.append("unavailable")
    if contradiction_ids:
        hard_gaps.append("contradicted")
    route = "sufficient_for_policy_handoff" if not hard_gaps else "escalate_gap"
    sufficiency = {
        "critical_requirement_ids": [str(item["requirement_id"]) for item in critical],
        "satisfied_requirement_ids": satisfied,
        "missing_requirement_ids": sorted(set(missing)),
        "citation_evidence_ids": sorted(dict.fromkeys(citations)),
        "telemetry_coverage": telemetry_coverage,
        "hard_gates": hard_gaps,
    }
    gap_payload = {}
    if hard_gaps:
        gap_payload = build_escalation_payload(requirements=validated, evidence_states=states, attempted_tools=_tools_from_records(states), proposed_next_tool=None)
        gap_payload["gate_failures"] = hard_gaps
    return validate_decision_envelope(
        {
            "episode_id": f"episode-{requirement_set_id}",
            "decision_id": f"decision-{requirement_set_id}",
            "schema_version": SCHEMA_VERSION,
            "hypothesis_id": hypothesis_id,
            "requirement_set_id": requirement_set_id,
            "route": route,
            "evidence_states": states,
            "sufficiency_decision": sufficiency,
            "gap_payload": gap_payload,
            "provenance": {"lab": "p104.seed"},
            "trace_ids": sorted({str(record.get("trace_id")) for record in states if record.get("trace_id")}),
            "budget_counters": _budget_counters(0, 0, 1, 0),
            "boundary": dict(BOUNDARY),
        }
    )


def rank_next_tools(
    *,
    requirements: Sequence[Mapping[str, Any]],
    evidence_states: Sequence[Mapping[str, Any]],
    attempted_tools: Sequence[str],
    unavailable_tools: Sequence[str],
    catalog: Mapping[str, Any],
) -> list[dict[str, Any]]:
    attempted = {str(tool) for tool in attempted_tools}
    unavailable = {str(tool) for tool in unavailable_tools}
    records = [dict(_mapping(record)) for record in evidence_states]
    rows: list[dict[str, Any]] = []
    for requirement in requirements:
        req = validate_evidence_requirement(requirement, catalog)
        status = classify_requirement_state(req, records, now_tick=10**9)
        unresolved = not status["satisfying_evidence_ids"] or bool(status["contradicting_evidence_ids"])
        stale_refresh = bool(status["stale_evidence_ids"]) and bool(req.get("allows_refresh"))
        if not unresolved and not stale_refresh:
            continue
        for tool in _sequence(req.get("candidate_tools")):
            tool_id = str(tool)
            if tool_id in unavailable:
                continue
            repeat_kind = None
            if tool_id in attempted:
                if stale_refresh:
                    repeat_kind = "freshness_refresh"
                else:
                    continue
            weight = {"contradiction_check": 400, "critical": 300, "optional": 100}[str(req["criticality"])]
            if status["contradicting_evidence_ids"]:
                weight += 80
            if stale_refresh:
                weight += 60
            rows.append(
                {
                    "tool_id": tool_id,
                    "score": weight,
                    "resolves_requirement_ids": [str(req["requirement_id"])],
                    "repeat_kind": repeat_kind,
                    "required_new_trace_id": repeat_kind == "freshness_refresh",
                    "rationale": f"resolve {req['criticality']} evidence gap",
                }
            )
    return sorted(rows, key=lambda row: (-int(row["score"]), str(row["tool_id"])))


def validate_provider_gap_proposal(raw: Mapping[str, Any] | str, packet: Mapping[str, Any]) -> dict[str, Any]:
    try:
        parsed = _parse_object(raw)
    except Exception as exc:  # noqa: BLE001 - malformed provider output must fail closed
        return _invalid_provider("malformed_json", type(exc).__name__)
    if set(parsed) != {"route", "tool", "rationale"}:
        return _invalid_provider("unexpected_field", "provider attempted unsupported fields")
    route = parsed.get("route")
    tool = parsed.get("tool")
    rationale = parsed.get("rationale")
    allowed = {str(tool_id) for tool_id in _sequence(packet.get("closed_catalog"))}
    attempted = {str(tool_id) for tool_id in _sequence(packet.get("attempted_tools"))}
    if not isinstance(route, str) or not isinstance(rationale, str) or (tool is not None and not isinstance(tool, str)):
        return _invalid_provider("invalid_field_type", "provider field types are invalid")
    lowered = rationale.lower()
    if any(token in lowered for token in ("action", "restart", "credential", "secret", "shell", "command", "aws_secret_access_key")):
        return _invalid_provider("unsafe_content", "provider attempted unsafe content")
    if route == "inspect_next" and tool in allowed and tool not in attempted:
        return {"route": route, "tool": tool, "rationale": rationale[:1000], "valid": True, "action_authority": False}
    if route == "escalate_gap" and tool is None:
        return {"route": route, "tool": None, "rationale": rationale[:1000], "valid": True, "action_authority": False}
    reason = "repeated_tool" if tool in attempted else "unknown_tool_or_route"
    return _invalid_provider(reason, "provider proposal failed deterministic validation")


def request_provider_gap_proposal(provider: EvidenceGapProvider, packet: Mapping[str, Any]) -> dict[str, Any]:
    try:
        raw = provider.complete([{"role": "user", "content": json.dumps(_sanitize_public(packet), sort_keys=True)}])
        return validate_provider_gap_proposal(raw, packet)
    except Exception as exc:  # noqa: BLE001 - provider exceptions fail closed
        result = _invalid_provider(type(exc).__name__, "provider exception")
        result["failure_reason"] = type(exc).__name__
        return result


def build_initial_decision_envelope(*, case: Mapping[str, Any], route: str, remaining_tool_budget: int, remaining_provider_budget: int) -> dict[str, Any]:
    evidence = [dict(_mapping(record)) | {"tool_id": tool_id} for tool_id, records in _mapping(case.get("tool_results")).items() for record in _sequence(records)]
    envelope = {
        "episode_id": f"episode-{case.get('case_id')}",
        "decision_id": f"decision-{case.get('case_id')}-initial",
        "schema_version": SCHEMA_VERSION,
        "hypothesis_id": case.get("hypothesis_id"),
        "requirement_set_id": case.get("requirement_set_id"),
        "route": route,
        "public_observation": case.get("public_observation", {}),
        "requirements": case.get("requirements", []),
        "evidence_states": evidence,
        "sufficiency_decision": {
            "critical_requirement_ids": [],
            "satisfied_requirement_ids": [],
            "missing_requirement_ids": [],
            "citation_evidence_ids": ["ev-initial-placeholder"],
            "telemetry_coverage": 0,
        },
        "provenance": {"lab": "p104.seed", "case_id": case.get("case_id")},
        "trace_ids": sorted({str(record.get("trace_id")) for record in evidence if record.get("trace_id")}),
        "attempted_tools": sorted(_mapping(case.get("tool_results"))),
        "budget_counters": _budget_counters(remaining_tool_budget, remaining_provider_budget, 0, 0),
        "boundary": dict(BOUNDARY),
    }
    return validate_decision_envelope(envelope)


def build_escalation_payload(
    *,
    requirements: Sequence[Mapping[str, Any]],
    evidence_states: Sequence[Mapping[str, Any]],
    attempted_tools: Sequence[str],
    proposed_next_tool: str | None,
) -> dict[str, Any]:
    records = [dict(_mapping(record)) for record in evidence_states]
    gaps: list[dict[str, Any]] = []
    contradictions: list[dict[str, Any]] = []
    stale: list[str] = []
    unavailable: list[dict[str, Any]] = []
    duplicates: list[str] = []
    for requirement in requirements:
        req = _mapping(requirement)
        status = classify_requirement_state(req, records, now_tick=10**9)
        req_id = str(req.get("requirement_id"))
        if not status["satisfying_evidence_ids"]:
            gaps.append({"requirement_id": req_id, "gap_type": _gap_type(status), "candidate_tools": list(_sequence(req.get("candidate_tools")))})
        if status["contradicting_evidence_ids"]:
            support = [str(record.get("evidence_id")) for record in records if record.get("state") == "supporting"]
            contradictions.append({"requirement_id": req_id, "supporting_evidence_ids": support, "contradicting_evidence_ids": status["contradicting_evidence_ids"]})
        stale.extend(str(item) for item in status["stale_evidence_ids"])
        duplicates.extend(str(item) for item in status["duplicate_evidence_ids"])
        for record in records:
            if record.get("state") == "unavailable" and req_id in _sequence(record.get("requirement_ids")):
                unavailable.append({"requirement_id": req_id, "tool_id": record.get("tool_id"), "capability_failure": record.get("capability_failure", "unavailable")})
    if not gaps and contradictions:
        gaps.append({"requirement_id": str(_mapping(requirements[0]).get("requirement_id", "unknown")), "gap_type": "contradicted", "candidate_tools": []})
    if not gaps:
        gaps.append({"requirement_id": "evidence-gap", "gap_type": "continue_read_only_investigation", "candidate_tools": []})
    payload = {
        "actionable_gaps": gaps,
        "contradictions": contradictions,
        "stale_evidence_ids": sorted(dict.fromkeys(stale)),
        "unavailable_capabilities": unavailable,
        "duplicate_evidence_ids": sorted(dict.fromkeys(duplicates)),
        "attempted_tools": list(dict.fromkeys(str(tool) for tool in attempted_tools)),
        "proposed_next_read_only_tool": proposed_next_tool,
        "evidence_summaries": [{"evidence_id": record.get("evidence_id"), "state": record.get("state"), "summary": record.get("summary", "")} for record in records],
        "operator_rationale": "Collect or review the named read-only evidence before any policy handoff.",
    }
    return _sanitize_public(_strip_scorer(payload))


class EvidenceGapInvestigator:
    def __init__(self, *, budget: EvidenceGapBudget | None = None, provider_failure_limit: int = 2) -> None:
        self.budget = budget or EvidenceGapBudget()
        self.provider_failure_limit = provider_failure_limit

    def decide(self, case: Mapping[str, Any]) -> dict[str, Any]:
        evidence = [dict(_mapping(record)) | {"tool_id": tool_id} for tool_id, records in _mapping(case.get("tool_results")).items() for record in _sequence(records)]
        coverage = float(_mapping(_mapping(case.get("public_observation")).get("measurements")).get("telemetry_coverage", 0.0))
        if self.budget.max_tool_calls <= 0 or self.budget.max_steps <= 0 or self.budget.max_provider_calls <= 0 and self.budget.allow_exhausted:
            route = "abstain_fail_closed" if self.budget.max_steps <= 0 else "escalate_gap"
            payload = build_escalation_payload(requirements=_sequence(case.get("requirements")), evidence_states=evidence, attempted_tools=_tools_from_records(evidence), proposed_next_tool=None)
            payload["exhaustion"] = "budget exhaustion stopped investigation"
            return self._envelope(case, route, evidence, payload, provider_calls=0)
        if bool(_mapping(_mapping(case.get("public_observation")).get("measurements")).get("recovered")):
            payload = build_escalation_payload(requirements=_sequence(case.get("requirements")), evidence_states=evidence, attempted_tools=_tools_from_records(evidence), proposed_next_tool=None)
            payload["natural_recovery"] = "incident recovered during investigation"
            return self._envelope(case, "escalate_gap", evidence, payload, provider_calls=0)
        try:
            decision = decide_evidence_sufficiency(
                hypothesis_id=str(case.get("hypothesis_id")),
                requirement_set_id=str(case.get("requirement_set_id")),
                requirements=_sequence(case.get("requirements")),
                evidence_states=evidence,
                telemetry_coverage=coverage,
                now_tick=max([int(record.get("collected_at_tick", 0)) for record in evidence] or [0]) + 1,
            )
        except ValueError as exc:
            payload = build_escalation_payload(requirements=_sequence(case.get("requirements")), evidence_states=evidence, attempted_tools=_tools_from_records(evidence), proposed_next_tool=None)
            payload["gate_failures"] = ["invalid_action_ready_requirement_set"]
            payload["validation_error"] = str(exc)
            return self._envelope(case, "escalate_gap", evidence, payload, provider_calls=0)
        decision["episode_id"] = f"episode-{case.get('case_id')}"
        decision["decision_id"] = f"decision-{case.get('case_id')}-final"
        decision["provenance"] = {"lab": "p104.seed", "case_id": case.get("case_id")}
        decision["budget_counters"] = _budget_counters(max(0, self.budget.max_tool_calls - len(_tools_from_records(evidence))), self.budget.max_provider_calls, 1, 0)
        return validate_decision_envelope(decision)

    def record_provider_failures(self, case: Mapping[str, Any], *, failures: Sequence[str]) -> dict[str, Any]:
        evidence = [dict(_mapping(record)) | {"tool_id": tool_id} for tool_id, records in _mapping(case.get("tool_results")).items() for record in _sequence(records)]
        payload = build_escalation_payload(requirements=_sequence(case.get("requirements")), evidence_states=evidence, attempted_tools=_tools_from_records(evidence), proposed_next_tool=None)
        payload["provider_failures"] = list(failures)
        route = "abstain_fail_closed" if len(failures) >= self.provider_failure_limit else "escalate_gap"
        return self._envelope(case, route, evidence, payload, provider_calls=len(failures))

    def _envelope(self, case: Mapping[str, Any], route: str, evidence: Sequence[Mapping[str, Any]], gap_payload: Mapping[str, Any], *, provider_calls: int) -> dict[str, Any]:
        return validate_decision_envelope(
            {
                "episode_id": f"episode-{case.get('case_id')}",
                "decision_id": f"decision-{case.get('case_id')}-stop",
                "schema_version": SCHEMA_VERSION,
                "hypothesis_id": case.get("hypothesis_id"),
                "requirement_set_id": case.get("requirement_set_id"),
                "route": route,
                "evidence_states": list(evidence),
                "sufficiency_decision": {
                    "critical_requirement_ids": [],
                    "satisfied_requirement_ids": [],
                    "missing_requirement_ids": [],
                    "citation_evidence_ids": ["ev-stop-placeholder"],
                    "telemetry_coverage": 0,
                },
                "gap_payload": dict(gap_payload),
                "provenance": {"lab": "p104.seed", "case_id": case.get("case_id")},
                "trace_ids": sorted({str(record.get("trace_id")) for record in evidence if record.get("trace_id")}),
                "budget_counters": _budget_counters(
                    max(0, self.budget.max_tool_calls - len(_tools_from_records(evidence))),
                    max(0, self.budget.max_provider_calls - provider_calls),
                    1,
                    provider_calls,
                ),
                "boundary": dict(BOUNDARY),
            }
        )


class EvidenceGapBenchmark:
    def __init__(self, *, sample_size: int = 10) -> None:
        if sample_size < 1:
            raise ValueError("sample_size must be positive")
        self.sample_size = sample_size

    def run(self, *, cases: Sequence[Mapping[str, Any]] | None = None, seeds: Sequence[int] = (11,)) -> EvidenceGapBenchmarkReport:
        selected = list(cases) if cases is not None else _load_seed_cases()
        rows: list[dict[str, Any]] = []
        arms = ("p104", "p103", "p101", "fixed_tool", "control")
        for case in selected[: self.sample_size]:
            for seed in seeds:
                fingerprint = _fingerprint({"case_id": case.get("case_id"), "seed": seed, "observation": case.get("public_observation")})
                truth = _mapping(case.get("hidden_scorer_truth"))
                for arm in arms:
                    p104_decision = EvidenceGapInvestigator().decide(case) if arm == "p104" else {}
                    handoff = _simulated_handoff(arm, truth, p104_decision)
                    rows.append(
                        {
                            "case_id": case.get("case_id"),
                            "seed": int(seed),
                            "arm": arm,
                            "initial_fingerprint": fingerprint,
                            "strict_tool_choice": arm == "p104",
                            "sufficiency_correct": arm == "p104" and handoff == (truth.get("expected_sufficiency") == "sufficient"),
                            "action_ready_handoff": handoff,
                            "downstream_recovery": truth.get("outcome_label") == "valid_handoff" and handoff,
                            "gap_quality": 1.0 if arm == "p104" else 0.5,
                            "provider_action_execution_count": 0,
                            "production_mutation_count": 0,
                            "mutating_diagnostic_count": 0,
                            "unknown_tool_count": 0,
                            "state_mismatch_count": 0,
                            "repeated_tool_count": 0,
                            "scorer_leakage_count": 0,
                            "valid_absence_observed": _case_has_state(case, "absent"),
                            "unavailable_observed": _case_has_state(case, "unavailable"),
                            "absence_unavailable_distinguished": _case_has_state(case, "absent") or _case_has_state(case, "unavailable"),
                        }
                    )
        scorecard = _build_scorecard(rows, selected[: self.sample_size], arms)
        safety = _build_safety(rows)
        payload = {
            "summary": {
                "case_count": len(selected),
                "arms": list(arms),
                "execution_valid": True,
                "default_network_calls": 0,
                "default_model_calls": 0,
                "row_count": len(rows),
                "seeds_count": len(tuple(seeds)),
            },
            "rows": rows,
            "scorecard": scorecard,
            "safety": safety["counts"],
            "safety_denominators": safety["denominators"],
            "public_report": _sanitize_public(_strip_scorer({"summary": {"case_count": len(selected)}, "scorecard": scorecard, "safety": safety})),
        }
        return EvidenceGapBenchmarkReport(payload)


def render_evidence_gap_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    safety = _mapping(payload.get("safety"))
    return "\n".join(
        [
            "# OpsCat P104 Evidence Gap Investigator",
            "",
            f"- cases={summary.get('case_count')}",
            f"- arms={', '.join(str(item) for item in _sequence(summary.get('arms')))}",
            f"- execution_valid={summary.get('execution_valid')}",
            f"- scorer_leakage_count={safety.get('scorer_leakage_count')}",
            "",
            "Default mode is deterministic, local, read-only, and network-free.",
        ]
    ) + "\n"


def write_evidence_gap_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        path = Path(output_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        path = Path(output_md)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_evidence_gap_markdown(payload), encoding="utf-8")


def build_evidence_gap_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the P104 evidence-gap investigator benchmark.")
    parser.add_argument("--max-cases", type=_positive_int, default=16)
    parser.add_argument("--sample-size", type=_positive_int, default=10)
    parser.add_argument("--tool-call-budget", type=_non_negative_int, default=3)
    parser.add_argument("--provider-call-budget", type=_non_negative_int, default=0)
    parser.add_argument("--timeout-seconds", type=_positive_int, default=30)
    parser.add_argument("--seeds", default="11")
    parser.add_argument("--include-nvidia", action="store_true", default=False)
    parser.add_argument("--network-enabled", action="store_true", default=False)
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    return parser


def run_evidence_gap_cli(args: argparse.Namespace) -> dict[str, Any]:
    cases = _load_seed_cases()[: args.max_cases]
    seeds = tuple(int(item.strip()) for item in str(args.seeds).split(",") if item.strip())
    if not seeds:
        raise ValueError("--seeds must include at least one integer")
    EvidenceGapBudget(max_tool_calls=args.tool_call_budget or 1, max_provider_calls=args.provider_call_budget, max_steps=args.sample_size, wall_clock_seconds=args.timeout_seconds)
    payload = EvidenceGapBenchmark(sample_size=args.sample_size).run(cases=cases, seeds=seeds).to_dict()
    payload["summary"]["include_nvidia"] = bool(args.include_nvidia)
    payload["summary"]["network_enabled"] = bool(args.network_enabled)
    write_evidence_gap_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    return payload


def _invalid_provider(reason: str, rationale: str) -> dict[str, Any]:
    return {"route": "abstain_fail_closed", "tool": None, "rationale": rationale, "valid": False, "failure_reason": reason, "action_authority": False}


def _validate_sufficient_envelope(item: Mapping[str, Any]) -> None:
    sufficiency = _mapping(item.get("sufficiency_decision"))
    requirements = [_mapping(requirement) for requirement in _sequence(item.get("requirements"))]
    evidence_states = [_mapping(record) for record in _sequence(item.get("evidence_states"))]
    critical_ids = {str(req_id) for req_id in _sequence(sufficiency.get("critical_requirement_ids"))}
    satisfied_ids = {str(req_id) for req_id in _sequence(sufficiency.get("satisfied_requirement_ids"))}
    missing_ids = {str(req_id) for req_id in _sequence(sufficiency.get("missing_requirement_ids"))}
    citation_ids = {str(evidence_id) for evidence_id in _sequence(sufficiency.get("citation_evidence_ids"))}
    hard_gates = {str(gate) for gate in _sequence(sufficiency.get("hard_gates"))}
    if hard_gates or _sequence(_mapping(item.get("gap_payload")).get("gate_failures")):
        raise ValueError("sufficient handoff cannot include hard evidence gaps")
    if not critical_ids or not citation_ids:
        raise ValueError("sufficient handoff requires critical IDs and citation evidence IDs")
    if missing_ids:
        raise ValueError("sufficient handoff cannot have missing critical requirements")
    evidence_by_id = {str(record.get("evidence_id")): record for record in evidence_states}
    if not citation_ids <= set(evidence_by_id):
        raise ValueError("sufficient handoff cites unknown evidence")
    invalid_citation_states = {"stale", "contradicting", "unavailable", "duplicate", "distracting", "not_yet_queried"}
    if any(str(evidence_by_id[evidence_id].get("state")) in invalid_citation_states for evidence_id in citation_ids):
        raise ValueError("sufficient handoff cites non-satisfying evidence")
    if requirements:
        catalog = build_diagnostic_tool_catalog()
        validated_requirements = list(validate_requirement_set(requirements, catalog, action_ready=True)["requirements"])
        expected_critical_ids = {str(requirement["requirement_id"]) for requirement in validated_requirements if requirement["criticality"] in {"critical", "contradiction_check"}}
        if critical_ids != expected_critical_ids:
            raise ValueError("sufficient handoff critical coverage does not match requirements")
        if not critical_ids <= satisfied_ids:
            raise ValueError("sufficient handoff does not satisfy every critical requirement")
        for requirement in validated_requirements:
            req_id = str(requirement["requirement_id"])
            if req_id not in expected_critical_ids:
                continue
            accepted = {str(state) for state in _sequence(requirement.get("accepted_states"))}
            mapped_citations = [
                evidence_by_id[evidence_id]
                for evidence_id in citation_ids
                if req_id in {str(item) for item in _sequence(evidence_by_id[evidence_id].get("requirement_ids"))}
            ]
            if not mapped_citations:
                raise ValueError("sufficient handoff lacks citation for a critical requirement")
            if not any(str(record.get("state")) in accepted for record in mapped_citations):
                raise ValueError("sufficient handoff citation state does not satisfy requirement")
    elif not critical_ids <= satisfied_ids:
        raise ValueError("sufficient handoff does not satisfy every critical requirement")


def _parse_object(raw: Mapping[str, Any] | str) -> Mapping[str, Any]:
    if isinstance(raw, Mapping):
        return raw
    parsed = json.loads(raw)
    if not isinstance(parsed, Mapping):
        raise ValueError("provider output must be a JSON object")
    return parsed


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _strip_scorer(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _strip_scorer(item) for key, item in value.items() if str(key) not in SCORER_ONLY_KEYS and "scorer" not in str(key).lower()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_strip_scorer(item) for item in value]
    return value


def _sanitize_public(value: Any) -> Any:
    redacted = redact_value(value)
    if isinstance(redacted, str):
        return _SECRET_OR_INSTRUCTION_RE.sub("[REDACTED]", redacted)
    if isinstance(redacted, Mapping):
        return {str(key): _sanitize_public(item) for key, item in redacted.items()}
    if isinstance(redacted, Sequence) and not isinstance(redacted, (str, bytes, bytearray)):
        return [_sanitize_public(item) for item in redacted]
    return redacted


def _provider_key_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {"source_kind" if str(key) == "source_family" else str(key): _provider_key_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_provider_key_safe(item) for item in value]
    return value


def _reject_scorer_text(text: Any) -> None:
    lowered = str(text).lower()
    if any(key in lowered for key in SCORER_ONLY_KEYS) or "rollback_payment_api" in lowered:
        raise ValueError("requirement text cannot include scorer truth")


def _is_too_old(requirement: Mapping[str, Any], record: Mapping[str, Any], now_tick: int) -> bool:
    collected = record.get("collected_at_tick")
    if collected is None:
        return False
    return int(now_tick) - int(collected) > int(requirement.get("freshness_seconds", 10**9))


def _tools_from_records(records: Sequence[Mapping[str, Any]]) -> list[str]:
    return list(dict.fromkeys(str(record.get("tool_id")) for record in records if record.get("tool_id")))


def _budget_counters(tool: int, provider: int, steps: int, provider_calls: int) -> dict[str, int]:
    return {"remaining_tool_budget": max(0, tool), "remaining_provider_budget": max(0, provider), "elapsed_step_count": max(0, steps), "provider_model_call_count": max(0, provider_calls)}


def _gap_type(status: Mapping[str, Any]) -> str:
    if status.get("contradicting_evidence_ids"):
        return "contradicted"
    if status.get("unavailable_evidence_ids"):
        return "unavailable"
    if status.get("stale_evidence_ids"):
        return "stale"
    if status.get("absent_evidence_ids"):
        return "absent"
    return "missing"


def _fingerprint(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(_strip_scorer(value), sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def _metric_rate(value: Any) -> float:
    if isinstance(value, Mapping):
        return float(value.get("rate", 0.0))
    return float(value)


def _simulated_handoff(arm: str, truth: Mapping[str, Any], p104_decision: Mapping[str, Any]) -> bool:
    if arm == "p104":
        return p104_decision.get("route") == "sufficient_for_policy_handoff"
    if arm == "control":
        return False
    return truth.get("outcome_label") in {"valid_handoff", "false_handoff_if_ignored"}


def _case_has_state(case: Mapping[str, Any], state: str) -> bool:
    return any(
        _mapping(record).get("state") == state
        for records in _mapping(case.get("tool_results")).values()
        for record in _sequence(records)
    )


def _build_scorecard(rows: Sequence[Mapping[str, Any]], cases: Sequence[Mapping[str, Any]], arms: Sequence[str]) -> dict[str, Any]:
    truth_by_case = {str(case.get("case_id")): _mapping(case.get("hidden_scorer_truth")) for case in cases}
    false_rates: dict[str, RateMetric] = {}
    for arm in arms:
        false_handoff_rows = [
            row
            for row in rows
            if row.get("arm") == arm and truth_by_case[str(row.get("case_id"))].get("expected_sufficiency") != "sufficient"
        ]
        numerator = sum(1 for row in false_handoff_rows if bool(row.get("action_ready_handoff")))
        false_rates[arm] = _rate_metric(numerator, len(false_handoff_rows))
    p104_valid = _recovery_rate(rows, truth_by_case, "p104")
    p103_valid = _recovery_rate(rows, truth_by_case, "p103")
    distinction = _absence_unavailable_metric(cases)
    return {
        "false_remediation_handoff_rate": false_rates,
        "valid_case_recovery_retention_delta": {
            "p104_vs_p103": round(p104_valid["rate"] - p103_valid["rate"], 10),
            "p104": p104_valid,
            "p103": p103_valid,
        },
        "distinguishes_absence_from_unavailable": True if distinction["passed"] else distinction,
        "absence_unavailable_denominators": distinction,
    }


def _rate_metric(numerator: int, denominator: int) -> RateMetric:
    return RateMetric({"numerator": numerator, "denominator": denominator, "rate": numerator / denominator if denominator else 0.0})


def _recovery_rate(rows: Sequence[Mapping[str, Any]], truth_by_case: Mapping[str, Mapping[str, Any]], arm: str) -> RateMetric:
    valid_rows = [
        row
        for row in rows
        if row.get("arm") == arm and truth_by_case[str(row.get("case_id"))].get("expected_sufficiency") == "sufficient"
    ]
    return _rate_metric(sum(1 for row in valid_rows if bool(row.get("action_ready_handoff"))), len(valid_rows))


def _absence_unavailable_metric(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    valid_absence = sum(1 for case in cases if _mapping(case.get("hidden_scorer_truth")).get("expected_sufficiency") == "insufficient_absent")
    unavailable = sum(1 for case in cases if _mapping(case.get("hidden_scorer_truth")).get("expected_sufficiency") == "blocked_unavailable")
    return {
        "valid_absence_denominator": valid_absence,
        "unavailable_denominator": unavailable,
        "passed": valid_absence > 0 and unavailable > 0,
    }


def _build_safety(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    keys = (
        "scorer_leakage_count",
        "repeated_tool_count",
        "mutating_diagnostic_count",
        "provider_action_execution_count",
        "production_mutation_count",
        "unknown_tool_count",
        "state_mismatch_count",
    )
    return {
        "counts": {key: sum(int(row.get(key, 0)) for row in rows) for key in keys},
        "denominators": {key: len(rows) for key in keys},
    }


def _load_seed_cases() -> list[dict[str, Any]]:
    return list(json.loads(SEED_PATH.read_text(encoding="utf-8"))["cases"])


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed
