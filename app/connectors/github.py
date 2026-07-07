"""GitHub draft issue connector with approval-gated dry-run previews."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.connectors.base import ConnectorCallRequest, ConnectorCallResult, ConnectorCapability
from app.services.redaction import redact_value


class GitHubDraftIssueConnector:
    """Build redacted GitHub issue previews without network calls or mutations."""

    connector_id = "github.issues"
    capabilities: Mapping[str, ConnectorCapability] = {
        "issues.write": ConnectorCapability(
            name="issues.write",
            description="Prepare an approval-gated GitHub draft issue preview; live issue creation is disabled.",
            risk_level="external_write",
            read_only=False,
            required_role="operator",
            requires_approval=True,
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
                error="GitHub issue creation is disabled; use dry_run=True for an audited draft preview.",
                output={"created": False, "dry_run_required": True},
            )

        repository = _clean_text(request.payload.get("repository"))
        title = _clean_text(request.payload.get("title"))
        body = _clean_text(request.payload.get("body"))
        if not repository or not title or not body:
            return ConnectorCallResult(
                connector_id=self.connector_id,
                capability=request.capability,
                ok=False,
                read_only=False,
                error="repository, title, and body are required for GitHub draft issue previews",
                output={"created": False, "dry_run": True},
            )
        if not _valid_repository(repository):
            return ConnectorCallResult(
                connector_id=self.connector_id,
                capability=request.capability,
                ok=False,
                read_only=False,
                error="repository must be in owner/name form",
                output={"created": False, "dry_run": True},
            )

        preview = redact_value(
            {
                "repository": repository,
                "title": title,
                "body": body,
                "incident_id": request.incident_id or _clean_text(request.payload.get("incident_id")) or "unassigned",
                "labels": _clean_sequence(request.payload.get("labels")),
                "assignees": _clean_sequence(request.payload.get("assignees")),
            }
        )
        return ConnectorCallResult(
            connector_id=self.connector_id,
            capability=request.capability,
            ok=True,
            read_only=False,
            evidence_summary=f"Dry-run GitHub draft issue preview for {preview['repository']} incident {preview['incident_id']}; no issue created.",
            output={"dry_run": True, "created": False, "preview": preview},
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


def _valid_repository(repository: str) -> bool:
    parts = repository.split("/")
    return len(parts) == 2 and all(part and part.replace("-", "").replace("_", "").replace(".", "").isalnum() for part in parts)
