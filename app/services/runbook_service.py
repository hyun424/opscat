"""Local deterministic runbook registry and planner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.models import Incident
from app.services.root_cause_service import RootCauseCandidate


@dataclass(frozen=True)
class RunbookStep:
    name: str
    action_type: str
    preconditions: tuple[str, ...]
    required_permission: str
    risk_hint: Literal["read_only", "low", "medium", "high", "prohibited"]
    dry_run_supported: bool
    rollback_expectation: str
    verification_check: str


@dataclass(frozen=True)
class Runbook:
    key: str
    title: str
    incident_classes: tuple[str, ...]
    steps: tuple[RunbookStep, ...]


RUNBOOKS: tuple[Runbook, ...] = (
    Runbook(
        key="deploy_regression",
        title="Recent deploy regression",
        incident_classes=("deploy", "rollback", "payment_bad_deploy", "payment_api_deploy_regression"),
        steps=(
            RunbookStep("collect deploy context", "mock.get_recent_deploys", ("incident_summary_present",), "mock:deploys:read", "read_only", True, "none", "deploy marker is present"),
            RunbookStep(
                "draft rollback",
                "mock.create_rollback_pr",
                ("bad_deploy_identified", "rollback_plan_present"),
                "mock:pull_requests:write",
                "medium",
                True,
                "rollback PR remains draft/mock",
                "mock recovery check passes",
            ),
        ),
    ),
    Runbook(
        key="api_5xx_spike",
        title="API 5xx spike diagnostics",
        incident_classes=("5xx", "timeout", "external", "gateway"),
        steps=(
            RunbookStep("collect error context", "mock.get_error_context", ("incident_summary_present",), "mock:context:read", "read_only", True, "none", "error sample is redacted"),
            RunbookStep(
                "open tracking ticket",
                "mock.create_incident_ticket",
                ("evidence_cited", "incident_summary_present"),
                "mock:tickets:write",
                "low",
                True,
                "mock ticket only",
                "ticket_id_recorded",
            ),
        ),
    ),
    Runbook(
        key="queue_backlog",
        title="Queue backlog recovery",
        incident_classes=("queue", "worker", "backlog", "heartbeat"),
        steps=(
            RunbookStep(
                "collect worker context",
                "mock.get_error_context",
                ("incident_summary_present",),
                "mock:context:read",
                "read_only",
                True,
                "none",
                "queue metrics collected",
            ),
            RunbookStep(
                "restart mock worker",
                "mock.execute_restart_worker",
                ("worker_target_confirmed",),
                "mock:workers:restart",
                "low",
                True,
                "single mock worker restart",
                "mock.verify_recovery",
            ),
        ),
    ),
    Runbook(
        key="connector_outage",
        title="Connector outage or missing secret",
        incident_classes=("connector", "missing secret", "config"),
        steps=(
            RunbookStep(
                "check connector health",
                "mock.get_runbook",
                ("connector_id_present",),
                "mock:runbooks:read",
                "read_only",
                True,
                "none",
                "connector health known",
            ),
        ),
    ),
    Runbook(
        key="diagnostic_only",
        title="Diagnostic-only human handoff",
        incident_classes=("unknown", "ambiguous", "low-confidence"),
        steps=(
            RunbookStep(
                "collect context only",
                "mock.get_error_context",
                ("incident_summary_present",),
                "mock:context:read",
                "read_only",
                True,
                "none",
                "evidence package created",
            ),
        ),
    ),
)


def select_runbook(incident: Incident, candidates: list[RootCauseCandidate]) -> Runbook:
    haystack = " ".join(
        [
            incident.service,
            incident.environment,
            incident.summary or "",
            incident.root_cause_candidate or "",
            str(incident.alert_payload),
            *(candidate.hypothesis for candidate in candidates[:2]),
        ]
    ).lower()
    top_confidence = candidates[0].confidence if candidates else incident.confidence or 0.0
    if top_confidence < 0.55:
        return get_runbook("diagnostic_only")
    for runbook in RUNBOOKS:
        if runbook.key == "diagnostic_only":
            continue
        if any(token in haystack for token in runbook.incident_classes):
            return runbook
    return get_runbook("diagnostic_only")


def get_runbook(key: str) -> Runbook:
    for runbook in RUNBOOKS:
        if runbook.key == key:
            return runbook
    raise KeyError(key)
