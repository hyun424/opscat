from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

IncidentState = Literal[
    "new",
    "queued",
    "investigating",
    "needs_more_context",
    "action_proposed",
    "waiting_approval",
    "executing",
    "verifying",
    "resolved",
    "escalated",
    "false_positive",
    "failed",
]
RiskLevel = Literal["read_only", "low", "medium", "high", "prohibited"]
PolicyDecision = Literal["ALLOW", "REQUIRE_APPROVAL", "DENY", "ESCALATE"]


class MockAlertRequest(BaseModel):
    scenario: str = "payment_api_deploy_regression"
    service: str | None = None
    environment: str = "staging"
    severity: Literal["low", "medium", "high", "critical"] = "high"
    message: str | None = None
    fingerprint: str | None = None


class EvidenceRead(BaseModel):
    id: str
    type: str
    source: str
    source_url: str | None
    content: str
    evidence_metadata: dict[str, Any]
    collected_at: datetime

    model_config = {"from_attributes": True}


class ActionRead(BaseModel):
    id: str
    action_type: str
    target: str
    environment: str
    risk_level: str
    requires_approval: bool
    rationale: str
    payload: dict[str, Any]
    preconditions: list[str]
    post_checks: list[str]
    evidence_ids: list[str]
    policy_decision: str
    policy_reasons: list[str]
    confidence: float | None = None
    escalation_required: bool = False
    escalation_decision: str | None = None
    escalation_reason: str | None = None
    escalation_payload: dict[str, Any] | None = None
    status: str
    execution_result: dict[str, Any] | None

    model_config = {"from_attributes": True}


class TimelineRead(BaseModel):
    id: str
    timestamp: datetime
    actor: str
    event_type: str
    content: str
    event_metadata: dict[str, Any]

    model_config = {"from_attributes": True}


class IncidentRead(BaseModel):
    id: str
    source: str
    status: str
    service: str
    environment: str
    severity: str
    summary: str | None
    root_cause_candidate: str | None
    confidence: float | None
    created_at: datetime
    updated_at: datetime
    evidence: list[EvidenceRead] = Field(default_factory=list)
    actions: list[ActionRead] = Field(default_factory=list)
    timeline: list[TimelineRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ApprovalRequest(BaseModel):
    decision: Literal["approve", "reject"]
    actor: str = "demo-user"
    reason: str | None = None


class ApprovalResponse(BaseModel):
    action: ActionRead
    incident: IncidentRead
    report: str | None = None


class NightAutopilotConfig(BaseModel):
    quiet_start: str = "22:00"
    quiet_end: str = "07:00"
    timezone: str = "Asia/Seoul"
    max_automatic_risk: RiskLevel = "low"
    max_attempts_per_incident: int = 1
    allowed_services: list[str] = Field(default_factory=lambda: ["payment-api", "worker"])
    allowed_environments: list[str] = Field(default_factory=lambda: ["staging", "dev"])
    escalation_contacts: list[str] = Field(default_factory=lambda: ["primary-oncall"])


class NightAutopilotResult(BaseModel):
    mode: str
    incidents_detected: int
    actions_taken: list[dict[str, Any]]
    escalations: list[dict[str, Any]]
    morning_report: str
