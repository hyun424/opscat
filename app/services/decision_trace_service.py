"""Decision trace conventions over existing evidence/timeline records."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.models import Evidence, Incident
from app.services.redaction import redact_text, redact_value
from app.services.timeline_service import add_timeline_event

AGENTIC_STAGES = ("observe", "correlate", "diagnose", "plan", "risk", "act", "verify")


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
    if stage not in AGENTIC_STAGES:
        raise ValueError(f"unknown agentic trace stage: {stage}")
    metadata = redact_value(
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
        source_url=f"trace://{incident.id}/{stage}",
        content=redact_text(f"{stage}: {decision}" + (f" — {reason}" if reason else "")),
        evidence_metadata=metadata,
    )
    incident.evidence.append(evidence)
    add_timeline_event(
        db,
        incident.id,
        tenant_id=incident.tenant_id,
        workspace_id=incident.workspace_id,
        actor="agent-trace",
        event_type=f"agent_{stage}",
        content=evidence.content,
        metadata=metadata if isinstance(metadata, dict) else {},
    )
    db.flush()
    return evidence


def render_trace_json(incident: Incident) -> str:
    entries = [item.evidence_metadata for item in incident.evidence if item.type == "decision_trace"]
    return json.dumps(redact_value(entries), indent=2, sort_keys=True, default=str)


def render_trace_markdown(incident: Incident) -> str:
    lines = [f"# Agent Decision Trace: {incident.id}", ""]
    by_stage = {item.evidence_metadata.get("stage"): item for item in incident.evidence if item.type == "decision_trace"}
    for stage in AGENTIC_STAGES:
        item = by_stage.get(stage)
        if item is None:
            lines.append(f"- **{stage}**: not recorded")
            continue
        metadata = item.evidence_metadata
        lines.append(f"- **{stage}**: {redact_text(str(metadata.get('decision') or item.content))}")
        if metadata.get("confidence") is not None:
            lines.append(f"  - Confidence: {metadata['confidence']}")
        if metadata.get("policy_result"):
            lines.append(f"  - Policy: `{redact_text(str(metadata['policy_result']))}`")
    return "\n".join(lines) + "\n"
