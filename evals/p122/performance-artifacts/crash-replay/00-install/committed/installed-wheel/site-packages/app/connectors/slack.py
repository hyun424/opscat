"""Slack wake-up connector with dry-run-only message previews."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.connectors.base import ConnectorCallRequest, ConnectorCallResult, ConnectorCapability
from app.services.redaction import redact_value


class SlackWakeUpConnector:
    """Build redacted Slack wake-up previews without performing real sends."""

    connector_id = "slack.wake_up"
    capabilities: Mapping[str, ConnectorCapability] = {
        "messages.write": ConnectorCapability(
            name="messages.write",
            description="Prepare a Slack wake-up message preview for an incident; real sends are disabled.",
            risk_level="external_message",
            read_only=False,
            required_role="operator",
        ),
    }

    def call(self, request: ConnectorCallRequest) -> ConnectorCallResult:
        if request.capability not in self.capabilities:
            return ConnectorCallResult(
                connector_id=self.connector_id,
                capability=request.capability,
                ok=False,
                read_only=False,
                error="unsupported capability",
            )
        if not request.dry_run:
            return ConnectorCallResult(
                connector_id=self.connector_id,
                capability=request.capability,
                ok=False,
                read_only=False,
                error="Slack real sends are disabled; retry with dry_run=True for an audited preview.",
                output={"sent": False, "dry_run_required": True},
            )

        channel = _clean_text(request.payload.get("channel"))
        reason = _clean_text(request.payload.get("wake_up_reason") or request.payload.get("reason"))
        summary = _clean_text(request.payload.get("summary"))
        if not channel or not reason or not summary:
            return ConnectorCallResult(
                connector_id=self.connector_id,
                capability=request.capability,
                ok=False,
                read_only=False,
                error="channel, wake_up_reason, and summary are required for Slack wake-up previews",
                output={"sent": False, "dry_run": True},
            )

        preview = redact_value(
            {
                "channel": channel,
                "incident_id": request.incident_id or _clean_text(request.payload.get("incident_id")) or "unassigned",
                "severity": _clean_text(request.payload.get("severity")) or "unknown",
                "wake_up_reason": reason,
                "summary": summary,
                "blocked_action": _clean_text(request.payload.get("blocked_action")),
                "runbook_url": _clean_text(request.payload.get("runbook_url")),
                "next_steps": _clean_sequence(request.payload.get("next_steps")),
            }
        )
        return ConnectorCallResult(
            connector_id=self.connector_id,
            capability=request.capability,
            ok=True,
            read_only=False,
            evidence_summary=f"Dry-run Slack wake-up preview for {preview['incident_id']} in {channel}; no message sent.",
            output={"dry_run": True, "sent": False, "preview": preview},
        )


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _clean_sequence(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, bytearray)):
        return [_clean_text(value)] if _clean_text(value) else []
    try:
        return [item for item in (_clean_text(item) for item in value) if item]
    except TypeError:
        cleaned = _clean_text(value)
        return [cleaned] if cleaned else []
