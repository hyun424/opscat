"""P119 diagnosis and evidence acquisition loop for frozen local fixtures."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p119_contract import exact_zero_authority_counters, reject_authority_boundary

P119_EVIDENCE_TAXONOMY = frozenset({"metric_window", "log_excerpt", "trace_span", "config_snapshot", "postcheck_probe", "rollback_probe"})


class P119EvidenceError(ValueError):
    """Raised when evidence acquisition must fail closed."""


@dataclass(frozen=True)
class P119EvidenceRequest:
    request_id: str
    incident_id: str
    fixture_id: str
    evidence_class: str
    source_ref: str
    budget_cost: int
    value_of_information: float
    request_hash: str


@dataclass(frozen=True)
class P119EvidenceReceipt:
    request_id: str
    evidence_id: str
    evidence_class: str
    source_hash: str
    receipt_hash: str
    redaction_receipt: Mapping[str, Any]
    authority_counter_snapshot: Mapping[str, int]


@dataclass(frozen=True)
class P119DiagnosisUpdate:
    outcome: str
    competing_hypothesis_ids: tuple[str, ...]
    contradiction_ids: tuple[str, ...]
    missing_evidence_classes: tuple[str, ...]
    requested_evidence_classes: tuple[str, ...]
    receipt_refs: tuple[str, ...]
    decision_reason: str
    authority_counter_snapshot: Mapping[str, int]


def build_evidence_request(data: Mapping[str, Any]) -> P119EvidenceRequest:
    evidence_class = _evidence_class(data.get("evidence_class"))
    fixture_id = _fixture(data.get("fixture_id"))
    reject_authority_boundary(data)
    budget_cost = _positive_int(data.get("budget_cost"), "invalid_budget_cost")
    voi = _float(data.get("value_of_information"), "invalid_value_of_information")
    request_id = _required_text(data, "request_id")
    incident_id = _required_text(data, "incident_id")
    source_ref = _required_text(data, "source_ref")
    request_hash = stable_hash(
        {
            "request_id": request_id,
            "incident_id": incident_id,
            "fixture_id": fixture_id,
            "evidence_class": evidence_class,
            "source_ref": source_ref,
            "budget_cost": budget_cost,
            "value_of_information": voi,
        }
    )
    return P119EvidenceRequest(
        request_id=request_id,
        incident_id=incident_id,
        fixture_id=fixture_id,
        evidence_class=evidence_class,
        source_ref=source_ref,
        budget_cost=budget_cost,
        value_of_information=voi,
        request_hash=request_hash,
    )


def acquire_fixture_evidence(request: P119EvidenceRequest, fixture_catalog: Mapping[str, Mapping[str, Any]], *, remaining_budget: int) -> P119EvidenceReceipt:
    if remaining_budget < request.budget_cost:
        raise P119EvidenceError("evidence_budget_exhausted")
    if request.value_of_information < 0:
        raise P119EvidenceError("value_of_information_negative")
    source = fixture_catalog.get(request.source_ref)
    if source is None:
        raise P119EvidenceError("missing_evidence")
    reject_authority_boundary(source)
    if source.get("fixture_id") != request.fixture_id:
        raise P119EvidenceError("fixture_target_mismatch")
    if source.get("evidence_class") != request.evidence_class:
        raise P119EvidenceError("evidence_class_mismatch")
    if source.get("contaminated") is True:
        raise P119EvidenceError("contaminated_evidence_source")
    source_hash = str(source.get("source_hash", ""))
    if not source_hash.startswith("sha256:"):
        raise P119EvidenceError("unhashable_evidence")
    receipt_base = {
        "request_hash": request.request_hash,
        "evidence_id": _required_text(source, "evidence_id"),
        "source_hash": source_hash,
        "authority_counter_snapshot": exact_zero_authority_counters(),
    }
    redaction = {"redacted": True, "receipt_hash": stable_hash({"source_hash": source_hash, "evidence_id": receipt_base["evidence_id"]})}
    return P119EvidenceReceipt(
        request_id=request.request_id,
        evidence_id=str(receipt_base["evidence_id"]),
        evidence_class=request.evidence_class,
        source_hash=source_hash,
        receipt_hash=stable_hash({**receipt_base, "redaction_receipt": redaction}),
        redaction_receipt=redaction,
        authority_counter_snapshot=exact_zero_authority_counters(),
    )


def update_diagnosis(
    *,
    hypotheses: Sequence[Mapping[str, Any]],
    visible_evidence_ids: Sequence[str],
    evidence_receipts: Sequence[P119EvidenceReceipt],
    missing_evidence_classes: Sequence[str],
    contradiction_ids: Sequence[str],
    evidence_attempts_remaining: int,
) -> P119DiagnosisUpdate:
    for hypothesis in hypotheses:
        reject_authority_boundary(hypothesis)
    hypothesis_ids = tuple(sorted(_required_text(hypothesis, "hypothesis_id") for hypothesis in hypotheses))
    contradictions = tuple(sorted(str(item) for item in contradiction_ids if item))
    missing = tuple(sorted(str(item) for item in missing_evidence_classes if item))
    if contradictions:
        outcome = "abstain"
        reason = "contradictory_evidence"
    elif missing and evidence_attempts_remaining > 0:
        outcome = "investigate_more"
        reason = "missing_required_evidence"
    elif missing:
        outcome = "escalate"
        reason = "evidence_budget_exhausted"
    elif not visible_evidence_ids and not evidence_receipts:
        outcome = "investigate_more"
        reason = "missing_evidence"
    else:
        outcome = "selection_pending"
        reason = "sealed_evidence_sufficient"
    return P119DiagnosisUpdate(
        outcome=outcome,
        competing_hypothesis_ids=hypothesis_ids,
        contradiction_ids=contradictions,
        missing_evidence_classes=missing,
        requested_evidence_classes=missing if outcome == "investigate_more" else (),
        receipt_refs=tuple(sorted(receipt.receipt_hash for receipt in evidence_receipts)),
        decision_reason=reason,
        authority_counter_snapshot=exact_zero_authority_counters(),
    )


def _evidence_class(value: Any) -> str:
    if not isinstance(value, str) or value not in P119_EVIDENCE_TAXONOMY:
        raise P119EvidenceError(f"unknown_evidence_class:{value}")
    return value


def _fixture(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith(("local:fixture:", "mock:fixture:", "sandbox:fixture:")):
        raise P119EvidenceError("invalid_fixture_id")
    return value


def _required_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise P119EvidenceError(f"missing_{key}")
    return value.strip()


def _positive_int(value: Any, error: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise P119EvidenceError(error)
    return value


def _float(value: Any, error: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise P119EvidenceError(error)
    return float(value)
