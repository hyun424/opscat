"""Deterministic root-cause candidate generation for correlated incidents."""

from __future__ import annotations

from dataclasses import dataclass

from app.models import Evidence, Incident
from app.services.redaction import redact_text


@dataclass(frozen=True)
class RootCauseCandidate:
    hypothesis: str
    confidence: float
    evidence: tuple[str, ...] = ()
    counter_evidence: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    recommended_next_diagnostic: str = "collect_more_context"


def generate_root_cause_candidates(incident: Incident, evidence: list[Evidence]) -> list[RootCauseCandidate]:
    text = " ".join([incident.summary or "", str(incident.alert_payload), *(item.content for item in evidence)]).lower()
    evidence_ids = tuple(item.id for item in evidence[:4])
    candidates: list[RootCauseCandidate] = []

    deploy_score = 0.35 + (0.35 if any(token in text for token in ("deploy", "release", "rollback", "v1.42")) else 0.0)
    timeout_score = 0.25 + (0.25 if any(token in text for token in ("timeout", "5xx", "error spike")) else 0.0)
    queue_score = 0.25 + (0.35 if any(token in text for token in ("queue", "worker", "backlog", "heartbeat")) else 0.0)
    config_score = 0.20 + (0.35 if any(token in text for token in ("missing", "secret", "config")) else 0.0)

    candidates.append(
        RootCauseCandidate(
            hypothesis="Recent deploy regression",
            confidence=_bounded(deploy_score + min(0.15, len(evidence) * 0.03)),
            evidence=evidence_ids,
            counter_evidence=tuple(item.id for item in evidence if "external" in item.content.lower())[:2],
            missing_evidence=() if "deploy" in text else ("deploy_marker",),
            recommended_next_diagnostic="mock.get_recent_deploys",
        )
    )
    candidates.append(
        RootCauseCandidate(
            hypothesis="External dependency timeout",
            confidence=_bounded(timeout_score + (0.1 if "provider" in text or "gateway" in text else 0.0)),
            evidence=evidence_ids[:3],
            counter_evidence=tuple(item.id for item in evidence if "deploy" in item.content.lower())[:2],
            missing_evidence=() if "latency" in text or "timeout" in text else ("dependency_latency",),
            recommended_next_diagnostic="mock.get_error_context",
        )
    )
    candidates.append(
        RootCauseCandidate(
            hypothesis="Worker queue degradation",
            confidence=_bounded(queue_score),
            evidence=evidence_ids[:3],
            missing_evidence=() if "queue" in text else ("queue_depth_metric",),
            recommended_next_diagnostic="mock.get_error_context",
        )
    )
    candidates.append(
        RootCauseCandidate(
            hypothesis="Missing secret or configuration",
            confidence=_bounded(config_score),
            evidence=evidence_ids[:2],
            missing_evidence=() if "missing" in text else ("connector_health",),
            recommended_next_diagnostic="connector.health",
        )
    )
    return sorted(candidates, key=lambda item: item.confidence, reverse=True)


def persist_top_root_cause(incident: Incident, candidates: list[RootCauseCandidate]) -> None:
    if not candidates:
        incident.root_cause_candidate = "No deterministic root-cause candidate"
        incident.confidence = 0.0
        return
    top = candidates[0]
    incident.root_cause_candidate = redact_text(top.hypothesis)
    incident.confidence = top.confidence


def _bounded(value: float) -> float:
    return round(max(0.0, min(0.99, value)), 2)
