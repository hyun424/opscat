"""Deterministic action registry and risk classification for OpsCat MVP."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.models.action import ActionMetadata, RiskLevel

PROHIBITED_ACTIONS: dict[str, str] = {
    "production.rollback": "Production rollback is disabled in the MVP.",
    "production.restart_service": (
        "Production service restarts require a future hardened integration and explicit approval flow."
    ),
    "database.mutate": "Database mutations are prohibited by default.",
    "shell.execute": "Arbitrary shell execution is prohibited.",
    "cloud.delete_resource": "Cloud deletion is prohibited by default.",
    "secret.read": "Secret access is prohibited for agent actions.",
}


DEFAULT_ACTION_REGISTRY: dict[str, ActionMetadata] = {
    "mock.get_error_context": ActionMetadata(
        name="mock.get_error_context",
        description="Read sanitized mock error context for an incident.",
        base_risk=RiskLevel.READ_ONLY,
        is_read_only=True,
        is_mutation=False,
        reversible=True,
        blast_radius="none",
        default_requires_approval=False,
        allowed_environments=("dev", "staging", "test", "local", "production"),
        required_capabilities=("mock:context:read",),
    ),
    "mock.get_recent_deploys": ActionMetadata(
        name="mock.get_recent_deploys",
        description="Read mock deployment history for the affected service.",
        base_risk=RiskLevel.READ_ONLY,
        is_read_only=True,
        is_mutation=False,
        reversible=True,
        blast_radius="none",
        default_requires_approval=False,
        allowed_environments=("dev", "staging", "test", "local", "production"),
        required_capabilities=("mock:deploys:read",),
    ),
    "mock.get_runbook": ActionMetadata(
        name="mock.get_runbook",
        description="Read the matching mock runbook.",
        base_risk=RiskLevel.READ_ONLY,
        is_read_only=True,
        is_mutation=False,
        reversible=True,
        blast_radius="none",
        default_requires_approval=False,
        allowed_environments=("dev", "staging", "test", "local", "production"),
        required_capabilities=("mock:runbooks:read",),
    ),
    "mock.search_prior_incidents": ActionMetadata(
        name="mock.search_prior_incidents",
        description="Search sanitized prior incident summaries.",
        base_risk=RiskLevel.READ_ONLY,
        is_read_only=True,
        is_mutation=False,
        reversible=True,
        blast_radius="none",
        default_requires_approval=False,
        allowed_environments=("dev", "staging", "test", "local", "production"),
        required_capabilities=("mock:incidents:read",),
    ),
    "report.generate": ActionMetadata(
        name="report.generate",
        description="Generate a local incident report artifact.",
        base_risk=RiskLevel.LOW,
        is_read_only=False,
        is_mutation=False,
        reversible=True,
        blast_radius="local incident record",
        default_requires_approval=False,
        required_capabilities=("report:write",),
        post_checks=("report_contains_evidence",),
    ),
    "timeline.add_note": ActionMetadata(
        name="timeline.add_note",
        description="Append an audit timeline note to the local incident.",
        base_risk=RiskLevel.LOW,
        is_read_only=False,
        is_mutation=False,
        reversible=True,
        blast_radius="local incident record",
        default_requires_approval=False,
        required_capabilities=("timeline:write",),
    ),
    "mock.create_incident_ticket": ActionMetadata(
        name="mock.create_incident_ticket",
        description="Create a mock incident ticket; no external issue tracker is called.",
        base_risk=RiskLevel.LOW,
        is_read_only=False,
        is_mutation=True,
        reversible=True,
        blast_radius="mock ticket system",
        default_requires_approval=True,
        allowed_environments=("dev", "staging", "test", "local", "production"),
        required_capabilities=("mock:tickets:write",),
        required_preconditions=("evidence_cited", "incident_summary_present"),
        post_checks=("ticket_id_recorded",),
    ),
    "mock.create_rollback_pr": ActionMetadata(
        name="mock.create_rollback_pr",
        description="Create a mock rollback PR draft; no GitHub API is called.",
        base_risk=RiskLevel.MEDIUM,
        is_read_only=False,
        is_mutation=True,
        reversible=True,
        blast_radius="mock repository draft",
        default_requires_approval=True,
        allowed_environments=("dev", "staging", "test", "local", "production"),
        required_capabilities=("mock:pull_requests:write",),
        required_preconditions=("bad_deploy_identified", "rollback_plan_present"),
        post_checks=("pr_url_recorded", "verify_recovery_after_merge"),
    ),
    "mock.execute_restart_worker": ActionMetadata(
        name="mock.execute_restart_worker",
        description="Simulate restarting a non-production worker.",
        base_risk=RiskLevel.LOW,
        is_read_only=False,
        is_mutation=True,
        reversible=True,
        blast_radius="single non-production worker",
        default_requires_approval=True,
        allowed_environments=("dev", "staging", "test", "local"),
        required_capabilities=("mock:workers:restart",),
        required_preconditions=("worker_target_confirmed",),
        post_checks=("mock.verify_recovery",),
    ),
    "mock.verify_recovery": ActionMetadata(
        name="mock.verify_recovery",
        description="Read mock recovery signal after an action.",
        base_risk=RiskLevel.READ_ONLY,
        is_read_only=True,
        is_mutation=False,
        reversible=True,
        blast_radius="none",
        default_requires_approval=False,
        allowed_environments=("dev", "staging", "test", "local", "production"),
        required_capabilities=("mock:verification:read",),
    ),
}


class RiskEngine:
    def __init__(self, registry: Mapping[str, ActionMetadata] | None = None) -> None:
        self._registry = dict(registry or DEFAULT_ACTION_REGISTRY)

    @property
    def registry(self) -> Mapping[str, ActionMetadata]:
        return self._registry

    def get_action(self, action_type: str) -> ActionMetadata | None:
        if action_type in PROHIBITED_ACTIONS:
            return ActionMetadata(
                name=action_type,
                description=PROHIBITED_ACTIONS[action_type],
                base_risk=RiskLevel.PROHIBITED,
                is_read_only=False,
                is_mutation=True,
                reversible=False,
                blast_radius="unbounded or production",
                default_requires_approval=False,
                allowed_environments=(),
                prohibited_reason=PROHIBITED_ACTIONS[action_type],
            )
        return self._registry.get(action_type)

    def classify(self, action_type: str, payload: Mapping[str, Any] | None = None) -> RiskLevel:
        action = self.get_action(action_type)
        if action is None:
            return RiskLevel.HIGH
        if action.prohibited_reason:
            return RiskLevel.PROHIBITED
        return action.base_risk
