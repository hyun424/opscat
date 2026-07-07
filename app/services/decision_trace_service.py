"""Read-model decision trace helpers for agentic incident review."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models import Evidence, Incident
from app.models.action import ActionRequest
from app.services.action_simulator import ActionSimulator
from app.services.redaction import redact_value
from app.services.timeline_service import add_timeline_event

DECISION_TRACE_STAGES: tuple[str, ...] = ("observe", "correlate", "diagnose", "plan", "critique", "risk", "act", "verify")


@dataclass(frozen=True)
class DecisionTraceEntry:
    stage: str
    title: str
    summary: str
    tenant_id: str
    workspace_id: str
    incident_id: str
    actor: str = "system"
    action_id: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    confidence: float | None = None
    policy_decision: str | None = None
    risk_level: str | None = None
    status: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "title": self.title,
            "summary": self.summary,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "incident_id": self.incident_id,
            "actor": self.actor,
            "action_id": self.action_id,
            "evidence_ids": self.evidence_ids,
            "confidence": self.confidence,
            "policy_decision": self.policy_decision,
            "risk_level": self.risk_level,
            "status": self.status,
            "details": self.details,
        }


def record_decision_trace(
    db: Session,
    incident: Incident,
    *,
    stage: str,
    decision: str,
    confidence: float | None = None,
    inputs: Mapping[str, Any] | None = None,
    output_ref: str | None = None,
    policy_result: Mapping[str, Any] | None = None,
    reason: str | None = None,
) -> Evidence:
    """Persist one redacted agentic decision trace entry.

    The read-model helpers below render the current incident state. This write
    helper keeps the agent loop compatible with that model by storing each
    observe/correlate/diagnose/plan/risk/act/verify decision as evidence and a
    timeline event without introducing a separate persistence table.
    """

    if stage not in DECISION_TRACE_STAGES:
        raise ValueError(f"unknown agentic trace stage: {stage}")

    metadata = _redacted_details(
        {
            "stage": stage,
            "decision": decision,
            "confidence": confidence,
            "inputs": dict(inputs or {}),
            "output_ref": output_ref,
            "policy_result": dict(policy_result or {}),
            "reason": reason,
        }
    )
    evidence = Evidence(
        incident_id=incident.id,
        tenant_id=incident.tenant_id,
        workspace_id=incident.workspace_id,
        type="decision_trace",
        source="agentic_loop",
        source_url=None,
        content=json.dumps(metadata, sort_keys=True),
        evidence_metadata=metadata,
    )
    db.add(evidence)
    add_timeline_event(
        db,
        incident.id,
        tenant_id=incident.tenant_id,
        workspace_id=incident.workspace_id,
        actor="agent",
        event_type=f"decision_trace.{stage}",
        content=f"{stage}: {decision}",
        metadata={"evidence_type": "decision_trace", "stage": stage, "output_ref": output_ref},
    )
    return evidence


def build_decision_trace(incident: Any) -> list[DecisionTraceEntry]:
    """Build a redacted seven-stage read model from an incident object or API dict."""

    incident_id = str(_get(incident, "id", ""))
    tenant_id = str(_get(incident, "tenant_id", "demo"))
    workspace_id = str(_get(incident, "workspace_id", "demo"))
    service = str(_get(incident, "service", "unknown"))
    environment = str(_get(incident, "environment", "unknown"))
    status = str(_get(incident, "status", "unknown"))
    severity = str(_get(incident, "severity", "unknown"))
    summary = _safe_text(_get(incident, "summary", ""))
    root_cause = _safe_text(_get(incident, "root_cause_candidate", "Unknown"))
    confidence = _safe_float(_get(incident, "confidence", None))
    fingerprint = _safe_text(_get(incident, "alert_fingerprint", ""))
    evidence = _as_list(_get(incident, "evidence", []))
    actions = _as_list(_get(incident, "actions", []))
    timeline = _as_list(_get(incident, "timeline", []))
    primary_action = actions[0] if actions else None
    action_id = str(_get(primary_action, "id", "")) if primary_action is not None else None
    evidence_ids = [str(_get(item, "id", "")) for item in evidence if str(_get(item, "id", ""))]

    critique = _latest_decision_trace(evidence, "critique")

    return [
        DecisionTraceEntry(
            stage="observe",
            title="Observed operational signal",
            summary=summary or f"{service} {severity} alert observed",
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            incident_id=incident_id,
            actor="integration",
            evidence_ids=evidence_ids,
            status=status,
            details=_redacted_details({"source": _get(incident, "source", ""), "severity": severity, "service": service, "environment": environment, "timeline": _timeline_summaries(timeline)}),
        ),
        DecisionTraceEntry(
            stage="correlate",
            title="Correlated incident context",
            summary=f"Grouped signal for {service} in {environment} with fingerprint {fingerprint[:12]}",
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            incident_id=incident_id,
            actor="agent",
            evidence_ids=evidence_ids,
            status=status,
            details=_redacted_details({"alert_fingerprint": fingerprint, "timeline_events": len(timeline), "evidence_count": len(evidence)}),
        ),
        DecisionTraceEntry(
            stage="diagnose",
            title="Root cause candidate",
            summary=root_cause or "Root cause candidate not available",
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            incident_id=incident_id,
            actor="agent",
            evidence_ids=evidence_ids,
            confidence=confidence,
            status=status,
            details=_redacted_details({"confidence": confidence, "supporting_evidence_ids": evidence_ids, "evidence": _evidence_summaries(evidence)}),
        ),
        DecisionTraceEntry(
            stage="plan",
            title="Runbook/action plan",
            summary=_action_summary(primary_action),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            incident_id=incident_id,
            actor="agent",
            action_id=action_id,
            evidence_ids=_action_evidence_ids(primary_action, evidence_ids),
            confidence=confidence,
            status=_safe_text(_get(primary_action, "status", status)) if primary_action is not None else status,
            details=_redacted_details({"preconditions": _get(primary_action, "preconditions", []), "post_checks": _get(primary_action, "post_checks", [])}),
        ),
        DecisionTraceEntry(
            stage="critique",
            title="Self-critique gate",
            summary=_critique_payload_summary(primary_action, critique),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            incident_id=incident_id,
            actor="agent",
            action_id=action_id,
            evidence_ids=_action_evidence_ids(primary_action, evidence_ids),
            confidence=confidence,
            status=_safe_text(_get(primary_action, "status", status)) if primary_action is not None else status,
            details=_redacted_details({"critique": _payload_value(primary_action, "self_critique"), "trace": critique}),
        ),
        DecisionTraceEntry(
            stage="risk",
            title="Risk decision",
            summary=_risk_summary(primary_action),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            incident_id=incident_id,
            actor="policy",
            action_id=action_id,
            evidence_ids=_action_evidence_ids(primary_action, evidence_ids),
            confidence=confidence,
            policy_decision=_safe_optional(_get(primary_action, "policy_decision", None)),
            risk_level=_safe_optional(_get(primary_action, "risk_level", None)),
            status=_safe_text(_get(primary_action, "status", status)) if primary_action is not None else status,
            details=_redacted_details(
                {
                    "policy_reasons": _get(primary_action, "policy_reasons", []),
                    "requires_approval": _get(primary_action, "requires_approval", None),
                    **_simulation_details(primary_action, incident),
                }
            ),
        ),
        DecisionTraceEntry(
            stage="act",
            title="Action status",
            summary=_act_summary(primary_action),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            incident_id=incident_id,
            actor="executor",
            action_id=action_id,
            evidence_ids=_action_evidence_ids(primary_action, evidence_ids),
            confidence=confidence,
            policy_decision=_safe_optional(_get(primary_action, "policy_decision", None)),
            risk_level=_safe_optional(_get(primary_action, "risk_level", None)),
            status=_safe_text(_get(primary_action, "status", status)) if primary_action is not None else status,
            details=_redacted_details({"execution_attempts": _attempt_summaries(primary_action)}),
        ),
        DecisionTraceEntry(
            stage="verify",
            title="Recovery verification",
            summary=_verification_summary(primary_action, status),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            incident_id=incident_id,
            actor="verifier",
            action_id=action_id,
            evidence_ids=_action_evidence_ids(primary_action, evidence_ids),
            confidence=confidence,
            policy_decision=_safe_optional(_get(primary_action, "policy_decision", None)),
            risk_level=_safe_optional(_get(primary_action, "risk_level", None)),
            status=status,
            details=_redacted_details({"incident_status": status, "post_checks": _latest_post_check(primary_action)}),
        ),
    ]


def render_trace_json(incident: Any) -> list[dict[str, Any]]:
    """Render the incident decision trace as redacted JSON-compatible dicts."""

    return [entry.to_dict() for entry in build_decision_trace(incident)]


def render_trace_markdown(incident: Any) -> str:
    """Render the incident decision trace as compact Markdown for reports."""

    lines = ["# Agent Decision Trace", ""]
    for entry in build_decision_trace(incident):
        lines.append(f"## {entry.stage}: {entry.title}")
        lines.append(f"- Summary: {entry.summary}")
        lines.append(f"- Status: {entry.status or 'unknown'}")
        if entry.confidence is not None:
            lines.append(f"- Confidence: {entry.confidence:.2f}")
        if entry.policy_decision:
            lines.append(f"- Policy: {entry.policy_decision}")
        if entry.risk_level:
            lines.append(f"- Risk: {entry.risk_level}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _timeline_summaries(timeline: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "event_type": _get(event, "event_type", ""),
            "content": _get(event, "content", ""),
        }
        for event in timeline[:8]
    ]


def _evidence_summaries(evidence: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": _get(item, "id", ""),
            "type": _get(item, "type", ""),
            "content": _get(item, "content", ""),
        }
        for item in evidence[:8]
    ]


def _action_summary(action: Any) -> str:
    if action is None:
        return "No action plan recorded yet"
    return f"Plan {_safe_text(_get(action, 'action_type', 'unknown'))} on {_safe_text(_get(action, 'target', 'unknown'))}"


def _risk_summary(action: Any) -> str:
    if action is None:
        return "Risk decision not recorded yet"
    return f"Policy {_safe_text(_get(action, 'policy_decision', 'unknown'))} with risk {_safe_text(_get(action, 'risk_level', 'unknown'))}"


def _critique_payload_summary(action: Any, trace: dict[str, Any]) -> str:
    critique = _payload_value(action, "self_critique")
    if critique:
        decision = _safe_text(critique.get("decision", "unknown"))
        missing = len(_as_list(critique.get("missing_evidence", [])))
        objections = len(_as_list(critique.get("action_risk_objections", [])))
        return f"Self-critique {decision}; missing={missing}; objections={objections}"
    if trace:
        return _safe_text(trace.get("decision", "self-critique recorded"))
    return "Self-critique not recorded yet"


def _act_summary(action: Any) -> str:
    if action is None:
        return "Action not proposed yet"
    attempts = _as_list(_get(action, "execution_attempts", []))
    return f"Action {_safe_text(_get(action, 'status', 'unknown'))}; attempts={len(attempts)}"


def _verification_summary(action: Any, incident_status: str) -> str:
    latest = _latest_post_check(action)
    if latest:
        recovered = latest.get("recovered")
        return f"Recovery verified={recovered}; incident status={incident_status}"
    return f"Verification pending; incident status={incident_status}"


def _attempt_summaries(action: Any) -> list[dict[str, Any]]:
    attempts = _as_list(_get(action, "execution_attempts", [])) if action is not None else []
    return [
        {
            "id": _get(attempt, "id", ""),
            "attempt_number": _get(attempt, "attempt_number", None),
            "status": _get(attempt, "status", ""),
            "retry_eligible": _get(attempt, "retry_eligible", False),
        }
        for attempt in attempts
    ]


def _latest_post_check(action: Any) -> dict[str, Any]:
    attempts = _as_list(_get(action, "execution_attempts", [])) if action is not None else []
    if not attempts:
        return {}
    latest = attempts[-1]
    value = _get(latest, "post_check_result", {})
    return dict(value) if isinstance(value, Mapping) else {}


def _payload_value(action: Any, key: str) -> dict[str, Any]:
    if action is None:
        return {}
    payload = _get(action, "payload", {})
    if not isinstance(payload, Mapping):
        return {}
    value = payload.get(key, {})
    return dict(value) if isinstance(value, Mapping) else {}


def _latest_decision_trace(evidence: list[Any], stage: str) -> dict[str, Any]:
    for item in reversed(evidence):
        metadata = _get(item, "evidence_metadata", {})
        if isinstance(metadata, Mapping) and metadata.get("stage") == stage:
            return dict(metadata)
    return {}


def _action_evidence_ids(action: Any, fallback: list[str]) -> list[str]:
    if action is None:
        return fallback
    values = _as_list(_get(action, "evidence_ids", []))
    return [str(value) for value in values if str(value)] or fallback


def _simulation_details(action: Any, incident: Any) -> dict[str, Any]:
    if action is None:
        return {}
    request = ActionRequest(
        action_type=str(_get(action, "action_type", "")),
        target=str(_get(action, "target", _get(incident, "service", "unknown"))),
        environment=str(_get(action, "environment", _get(incident, "environment", "local"))),
        tenant_id=str(_get(action, "tenant_id", _get(incident, "tenant_id", "demo"))),
        workspace_id=str(_get(action, "workspace_id", _get(incident, "workspace_id", "demo"))),
        payload=_as_mapping(_get(action, "payload", {})),
        incident_id=str(_get(action, "incident_id", _get(incident, "id", ""))),
        approved=str(_get(action, "policy_decision", "")) == "ALLOW",
    )
    simulation = ActionSimulator().simulate(request).to_dict()
    return {"blast_radius": simulation["blast_radius"], "simulation": simulation}


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _redacted_details(value: dict[str, Any]) -> dict[str, Any]:
    redacted = redact_value(value)
    return dict(redacted) if isinstance(redacted, Mapping) else {}


def _safe_text(value: Any) -> str:
    redacted = redact_value("" if value is None else str(value))
    return str(redacted)


def _safe_optional(value: Any) -> str | None:
    if value is None:
        return None
    return _safe_text(value)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _critique_summary(evidence: list[Any], primary_action: Any, confidence: float | None) -> str:
    reasons = _critique_details(evidence)
    policy_reasons = _as_list(_get(primary_action, "policy_reasons", [])) if primary_action is not None else []
    if confidence is not None and confidence < 0.7:
        reasons.append("low confidence")
    reasons.extend(str(reason) for reason in policy_reasons if "confidence" in str(reason).lower() or "evidence" in str(reason).lower())
    return "; ".join(reasons[:3]) if reasons else "No self-critique blockers found before action proposal"


def _critique_details(evidence: list[Any]) -> list[str]:
    details: list[str] = []
    text = "\n".join(_safe_text(_get(item, "content", "")).lower() for item in evidence)
    for marker in ("conflict", "ambiguous", "unknown", "poison", "injection"):
        if marker in text:
            details.append(f"{marker} marker present")
    if len(evidence) < 2:
        details.append("missing evidence")
    return details
