"""P8 incident war-room read model.

Pure local/mock assembler: no provider, network, shell, auth, or mutation work.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from app.models import Incident
from app.services.agent_reliability_score import score_agent_reliability
from app.services.decision_trace_service import render_trace_json
from app.services.redaction import redact_text, redact_value
from app.services.root_cause_service import generate_root_cause_candidates


def build_war_room(incident: Incident | Mapping[str, Any]) -> dict[str, Any]:
    evidence = _as_list(_get(incident, "evidence", []))
    actions = _as_list(_get(incident, "actions", []))
    timeline = _as_list(_get(incident, "timeline", []))
    primary_action = actions[0] if actions else None
    score = score_agent_reliability(_score_inputs(incident, evidence, primary_action))
    score_payload = score.to_dict()
    root_cause_candidates = _root_cause_candidates(incident, evidence)
    policy_decision = _policy_decision(primary_action)
    return _redacted_dict(
        {
            "incident_id": str(_get(incident, "id", "")),
            "tenant_id": str(_get(incident, "tenant_id", "demo")),
            "workspace_id": str(_get(incident, "workspace_id", "demo")),
            "local_mock_only": True,
            "status": str(_get(incident, "status", "unknown")),
            "impact": {
                "service": str(_get(incident, "service", "unknown")),
                "environment": str(_get(incident, "environment", "unknown")),
                "severity": str(_get(incident, "severity", "unknown")),
            },
            "summary": _get(incident, "summary", ""),
            "timeline": _timeline(timeline),
            "decision_trace": render_trace_json(incident),
            "current_hypothesis": _get(incident, "root_cause_candidate", None) or "No deterministic root-cause candidate recorded yet",
            "root_cause_candidates": root_cause_candidates,
            "hypotheses": root_cause_candidates,
            "evidence": _evidence(evidence),
            "missing_evidence": _missing_evidence(incident, evidence, primary_action),
            "proposed_action": _proposed_action(primary_action),
            "policy_decision": policy_decision,
            "policy_gates": _policy_gates(policy_decision),
            "blast_radius": _payload_section(primary_action, "blast_radius") or {"scope": "unknown", "allowed_for_auto": False},
            "simulation": _payload_section(primary_action, "simulation") or {"status": "not_recorded", "ok": False, "success": False},
            "memory_matches": _memory_matches(primary_action),
            "reliability_gates": {
                "hard_policy_blocked": score.hard_policy_blocked,
                "action_route": score.action_route,
                "human_on_exception_reason": score.human_on_exception_reason,
                "components_by_name": score_payload["components_by_name"],
            },
            "human_questions": _human_questions(score, primary_action),
            "runbook_critique": _runbook_critique(primary_action),
            "why_not_auto_execute": _why_not_auto_execute(score, policy_decision),
            "final_decision": _final_decision(incident, primary_action, score),
            "reliability_score": score_payload,
        }
    )


class WarRoomService:
    def build(self, incident: Incident | Mapping[str, Any]) -> dict[str, Any]:
        return build_war_room(incident)


def _root_cause_candidates(incident: Incident | Mapping[str, Any], evidence: list[Any]) -> list[dict[str, Any]]:
    try:
        candidates = generate_root_cause_candidates(incident, evidence)
    except Exception:
        candidates = []
    rows: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates[:3], start=1):
        rows.append(
            {
                "rank": index,
                "hypothesis": candidate.hypothesis,
                "confidence": candidate.confidence,
                "evidence_ids": list(candidate.evidence),
                "counter_evidence_ids": list(candidate.counter_evidence),
                "missing_evidence": list(candidate.missing_evidence),
                "recommended_next_diagnostic": candidate.recommended_next_diagnostic,
            }
        )
    return rows


def _timeline(timeline: list[Any]) -> list[dict[str, Any]]:
    events = sorted(timeline, key=lambda event: (_iso(_get(event, "timestamp", "")), str(_get(event, "id", ""))))
    return [
        {
            "id": str(_get(event, "id", "")),
            "timestamp": _iso(_get(event, "timestamp", "")),
            "actor": _get(event, "actor", "system"),
            "event_type": _get(event, "event_type", "unknown"),
            "content": _get(event, "content", ""),
            "metadata": _get(event, "event_metadata", {}),
        }
        for event in events
    ]


def _evidence(evidence: list[Any]) -> list[dict[str, Any]]:
    rows = sorted(evidence, key=lambda item: (_iso(_get(item, "collected_at", "")), str(_get(item, "id", ""))))
    return [
        {
            "id": str(_get(item, "id", "")),
            "type": _get(item, "type", "unknown"),
            "source": _get(item, "source", "mock"),
            "content": _get(item, "content", ""),
            "metadata": _get(item, "evidence_metadata", {}),
        }
        for item in rows
    ]


def _missing_evidence(incident: Incident | Mapping[str, Any], evidence: list[Any], action: Any) -> list[str]:
    missing: list[str] = []
    for candidate in _root_cause_candidates(incident, evidence):
        missing.extend(str(item) for item in candidate.get("missing_evidence", []))
    critique = _payload_section(action, "self_critique")
    missing.extend(str(item) for item in _as_list(critique.get("missing_evidence", [])))
    return sorted(set(missing))


def _proposed_action(action: Any) -> dict[str, Any] | None:
    if action is None:
        return None
    return {
        "id": str(_get(action, "id", "")),
        "action_type": _get(action, "action_type", "unknown"),
        "target": _get(action, "target", "unknown"),
        "status": _get(action, "status", "unknown"),
        "risk_level": _get(action, "risk_level", "unknown"),
        "requires_approval": bool(_get(action, "requires_approval", True)),
        "rationale": _get(action, "rationale", ""),
        "preconditions": _as_list(_get(action, "preconditions", [])),
        "post_checks": _as_list(_get(action, "post_checks", [])),
        "evidence_ids": _as_list(_get(action, "evidence_ids", [])),
    }


def _policy_decision(action: Any) -> dict[str, Any]:
    if action is None:
        return {"decision": "not_recorded", "reasons": ["No action proposed yet"], "requires_approval": True}
    return {
        "decision": str(_get(action, "policy_decision", "not_recorded")),
        "reasons": _as_list(_get(action, "policy_reasons", [])),
        "requires_approval": bool(_get(action, "requires_approval", True)),
    }


def _policy_gates(policy_decision: dict[str, Any]) -> list[dict[str, Any]]:
    decision = str(policy_decision.get("decision", "not_recorded"))
    reasons = _as_list(policy_decision.get("reasons", []))
    requires_approval = bool(policy_decision.get("requires_approval", True))
    status = "passed" if decision in {"ALLOW", "REQUIRE_APPROVAL"} else "blocked"
    gates = [
        {"name": "policy_decision", "status": status, "reason": decision},
        {
            "name": "approval_required",
            "status": "needs_human" if requires_approval else "passed",
            "reason": "human approval required" if requires_approval else "no approval required",
        },
    ]
    gates.extend({"name": "policy_reason", "status": "info", "reason": str(reason)} for reason in reasons)
    return gates


def _payload_section(action: Any, key: str) -> dict[str, Any]:
    if action is None:
        return {}
    payload = _get(action, "payload", {})
    if not isinstance(payload, Mapping):
        return {}
    value = payload.get(key, {})
    return dict(value) if isinstance(value, Mapping) else {}


def _memory_matches(action: Any) -> list[dict[str, Any]]:
    memory = _payload_section(action, "incident_memory")
    matches = memory.get("similar_incidents", [])
    if isinstance(matches, Sequence) and not isinstance(matches, (str, bytes, bytearray)):
        return [dict(item) if isinstance(item, Mapping) else {"value": item} for item in matches]
    return []


def _human_questions(score: Any, action: Any) -> list[dict[str, str]]:
    questions: list[dict[str, str]] = []
    critique = _payload_section(action, "self_critique")
    for item in _as_list(critique.get("missing_evidence", [])):
        questions.append({"question": f"Can you provide {item}?", "why_it_matters": "OpsCat needs this local/mock evidence before action."})
    if score.human_on_exception_reason:
        questions.append({"question": "Should the operator keep this incident in human review?", "why_it_matters": score.human_on_exception_reason})
    if not questions:
        questions.append({"question": "Is there any operator context missing from the local/mock evidence?", "why_it_matters": "Additional context can reduce ambiguity before approval."})
    return questions


def _runbook_critique(action: Any) -> dict[str, Any]:
    embedded = _payload_section(action, "runbook_critique")
    if embedded:
        return embedded
    self_critique = _payload_section(action, "self_critique")
    if self_critique:
        missing = _as_list(self_critique.get("missing_evidence", []))
        objections = _as_list(self_critique.get("action_risk_objections", []))
        fit = "weak_fit" if missing or objections else "good_fit"
        return {"fit": fit, "reasons": missing + objections, "suggestions": ["keep remediation local/mock and policy-gated"]}
    return {
        "fit": "insufficient_evidence",
        "reasons": ["no runbook critique payload recorded"],
        "suggestions": ["review local/mock evidence before action"],
    }


def _why_not_auto_execute(score: Any, policy_decision: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if score.human_on_exception_reason:
        reasons.append(str(score.human_on_exception_reason))
    if bool(policy_decision.get("requires_approval", True)):
        reasons.append("human approval required")
    if str(policy_decision.get("decision", "")) not in {"ALLOW", "REQUIRE_APPROVAL"}:
        reasons.append(f"policy decision {policy_decision.get('decision', 'not_recorded')}")
    return sorted(set(reasons)) or ["execution remains policy-gated and local/mock only"]


def _final_decision(incident: Incident | Mapping[str, Any], action: Any, score: Any) -> dict[str, Any]:
    action_status = str(_get(action, "status", "not_proposed")) if action is not None else "not_proposed"
    route = score.action_route if hasattr(score, "action_route") else "human_required"
    return {
        "incident_status": str(_get(incident, "status", "unknown")),
        "action_status": action_status,
        "route": route,
        "summary": f"Incident {_get(incident, 'status', 'unknown')}; action {action_status}; route {route}.",
    }


def _score_inputs(incident: Incident | Mapping[str, Any], evidence: list[Any], action: Any) -> dict[str, Any]:
    blast_radius = _payload_section(action, "blast_radius")
    simulation = _payload_section(action, "simulation")
    memory_matches = _memory_matches(action)
    latest_post_check = _latest_post_check(action)
    text = "\n".join(str(_get(item, "content", "")) for item in evidence).lower()
    memory_outcome = "none"
    if any(match.get("failed_prior_action") or match.get("outcome") in {"failed", "stale", "poisoned"} for match in memory_matches):
        memory_outcome = "failed"
    elif memory_matches:
        memory_outcome = str(memory_matches[0].get("outcome", "unknown"))
    return {
        "replay_pass_rate": 1.0,
        "dangerous_action_block_rate": 1.0,
        "confidence": _get(action, "confidence", None) if action is not None else _get(incident, "confidence", 0.0),
        "evidence_count": len(evidence),
        "conflicting_signals": any(marker in text for marker in ("conflict", "ambiguous", "contradiction")),
        "known_ambiguity": bool(_payload_section(action, "self_critique").get("requires_human", False)),
        "blast_radius_scope": blast_radius.get("scope") or blast_radius.get("level") or "unknown",
        "simulation_status": simulation.get("status", "not_recorded"),
        "memory_prior_outcome": memory_outcome,
        "post_action_verification": latest_post_check,
        "policy_decision": _get(action, "policy_decision", "not_recorded") if action is not None else "not_recorded",
    }


def _latest_post_check(action: Any) -> str:
    attempts = _as_list(_get(action, "execution_attempts", [])) if action is not None else []
    if not attempts:
        return "pending"
    result = _get(attempts[-1], "post_check_result", {})
    if isinstance(result, Mapping):
        if result.get("recovered") is True:
            return "passed"
        if result.get("recovered") is False:
            return "failed"
        return str(result.get("status") or "pending")
    return "pending"


def _redacted_dict(value: dict[str, Any]) -> dict[str, Any]:
    redacted = redact_value(value)
    return dict(redacted) if isinstance(redacted, Mapping) else value


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return redact_text(str(value or ""))


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)
