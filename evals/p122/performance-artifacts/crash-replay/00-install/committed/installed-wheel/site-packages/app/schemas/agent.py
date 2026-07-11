from typing import Any, Literal

from pydantic import BaseModel, Field


class Hypothesis(BaseModel):
    title: str
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence_ids: list[str]
    refuting_evidence_ids: list[str] = Field(default_factory=list)
    status: Literal["supported", "weak", "refuted", "unknown"]


class RecommendedAction(BaseModel):
    action_type: str
    target: str
    risk_level: Literal["read_only", "low", "medium", "high", "prohibited"]
    requires_approval: bool
    rationale: str
    payload: dict[str, Any] = Field(default_factory=dict)
    preconditions: list[str]
    post_checks: list[str]
    evidence_ids: list[str] = Field(default_factory=list)


class AgentAnalysis(BaseModel):
    summary: str
    affected_service: str
    environment: str
    severity: Literal["low", "medium", "high", "critical"]
    hypotheses: list[Hypothesis]
    recommended_action: RecommendedAction
    verification_plan: list[str]
    escalation_condition: str
