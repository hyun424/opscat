from dataclasses import dataclass, field

RiskRank = {"read_only": 0, "low": 1, "medium": 2, "high": 3, "prohibited": 4}


@dataclass(frozen=True)
class ActionDefinition:
    name: str
    description: str
    base_risk: str
    mutates: bool
    reversible: bool
    blast_radius: str
    default_requires_approval: bool
    allowed_environments: set[str]
    required_capabilities: set[str] = field(default_factory=set)
    required_preconditions: tuple[str, ...] = ()
    post_checks: tuple[str, ...] = ()


ACTION_REGISTRY: dict[str, ActionDefinition] = {
    "mock.get_error_context": ActionDefinition(
        "mock.get_error_context",
        "Read sanitized error window from mock observability.",
        "read_only",
        False,
        True,
        "incident",
        False,
        {"dev", "staging", "prod"},
    ),
    "mock.get_recent_deploys": ActionDefinition(
        "mock.get_recent_deploys",
        "Read recent mock deploys.",
        "read_only",
        False,
        True,
        "service",
        False,
        {"dev", "staging", "prod"},
    ),
    "mock.get_runbook": ActionDefinition(
        "mock.get_runbook",
        "Read machine runbook.",
        "read_only",
        False,
        True,
        "service",
        False,
        {"dev", "staging", "prod"},
    ),
    "mock.search_prior_incidents": ActionDefinition(
        "mock.search_prior_incidents",
        "Read prior incident summaries.",
        "read_only",
        False,
        True,
        "tenant",
        False,
        {"dev", "staging", "prod"},
    ),
    "mock.create_incident_ticket": ActionDefinition(
        "mock.create_incident_ticket",
        "Create a mock incident ticket artifact.",
        "low",
        True,
        True,
        "team",
        True,
        {"dev", "staging", "prod"},
        {"tickets:write"},
        ("incident has summary",),
        ("ticket reference stored on timeline",),
    ),
    "mock.create_rollback_pr": ActionDefinition(
        "mock.create_rollback_pr",
        "Create a mock rollback pull request draft; it never deploys code.",
        "medium",
        True,
        True,
        "repository",
        True,
        {"dev", "staging"},
        {"pull_requests:write"},
        ("bad deploy evidence present", "rollback target identified"),
        ("mock recovery check passes", "report includes PR reference"),
    ),
    "mock.execute_restart_worker": ActionDefinition(
        "mock.execute_restart_worker",
        "Execute a mock restart of a non-production worker only.",
        "low",
        True,
        True,
        "single non-prod worker",
        True,
        {"dev", "staging"},
        {"workers:restart:nonprod"},
        ("runbook marks restart reversible",),
        ("worker heartbeat is healthy",),
    ),
    "mock.verify_recovery": ActionDefinition(
        "mock.verify_recovery",
        "Read mock recovery metric after action.",
        "read_only",
        False,
        True,
        "incident",
        False,
        {"dev", "staging", "prod"},
    ),
    "prohibited.arbitrary_shell": ActionDefinition(
        "prohibited.arbitrary_shell",
        "Arbitrary shell execution is prohibited by default.",
        "prohibited",
        True,
        False,
        "unbounded",
        True,
        set(),
    ),
    "prohibited.database_mutation": ActionDefinition(
        "prohibited.database_mutation",
        "Database mutation is prohibited by default.",
        "prohibited",
        True,
        False,
        "database",
        True,
        set(),
    ),
}


def get_action_definition(action_type: str) -> ActionDefinition:
    if action_type not in ACTION_REGISTRY:
        return ActionDefinition(
            action_type,
            "Unknown action; escalate for human review.",
            "high",
            True,
            False,
            "unknown",
            True,
            set(),
        )
    return ACTION_REGISTRY[action_type]


def risk_at_most(actual: str, maximum: str) -> bool:
    return RiskRank[actual] <= RiskRank[maximum]
