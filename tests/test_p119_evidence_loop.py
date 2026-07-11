from __future__ import annotations

import pytest

from app.services.p119_evidence_loop import P119EvidenceError, acquire_fixture_evidence, build_evidence_request, update_diagnosis


def test_evidence_request_and_receipt_are_typed_budgeted_and_hash_bound() -> None:
    request = build_evidence_request(_request())
    receipt = acquire_fixture_evidence(request, _catalog(), remaining_budget=2)
    diagnosis = update_diagnosis(
        hypotheses=[{"hypothesis_id": "h1", "fault": "latency"}, {"hypothesis_id": "h2", "fault": "cpu"}],
        visible_evidence_ids=["ev-metric"],
        evidence_receipts=[receipt],
        missing_evidence_classes=[],
        contradiction_ids=[],
        evidence_attempts_remaining=1,
    )

    assert request.request_hash.startswith("sha256:")
    assert receipt.receipt_hash.startswith("sha256:")
    assert receipt.redaction_receipt["redacted"] is True
    assert diagnosis.outcome == "selection_pending"
    assert diagnosis.competing_hypothesis_ids == ("h1", "h2")


def test_evidence_loop_preserves_missing_evidence_contradictions_and_budget_exhaustion() -> None:
    missing = update_diagnosis(
        hypotheses=[{"hypothesis_id": "h1"}],
        visible_evidence_ids=[],
        evidence_receipts=[],
        missing_evidence_classes=["metric_window"],
        contradiction_ids=[],
        evidence_attempts_remaining=1,
    )
    contradictory = update_diagnosis(
        hypotheses=[{"hypothesis_id": "h1"}],
        visible_evidence_ids=["ev-a", "ev-b"],
        evidence_receipts=[],
        missing_evidence_classes=[],
        contradiction_ids=["c1"],
        evidence_attempts_remaining=1,
    )
    exhausted = update_diagnosis(
        hypotheses=[{"hypothesis_id": "h1"}],
        visible_evidence_ids=[],
        evidence_receipts=[],
        missing_evidence_classes=["trace_span"],
        contradiction_ids=[],
        evidence_attempts_remaining=0,
    )

    assert missing.outcome == "investigate_more"
    assert missing.requested_evidence_classes == ("metric_window",)
    assert contradictory.outcome == "abstain"
    assert contradictory.contradiction_ids == ("c1",)
    assert exhausted.outcome == "escalate"
    assert exhausted.decision_reason == "evidence_budget_exhausted"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda request: request.__setitem__("evidence_class", "live_connector"), "unknown_evidence_class"),
        (lambda request: request.__setitem__("fixture_id", "staging:checkout"), "invalid_fixture_id"),
        (lambda request: request.__setitem__("value_of_information", -0.1), "value_of_information_negative"),
    ],
)
def test_evidence_red_cases_fail_closed(mutate: object, message: str) -> None:
    request_payload = _request()
    mutate(request_payload)  # type: ignore[operator]
    if message == "value_of_information_negative":
        request = build_evidence_request(request_payload)
        with pytest.raises(P119EvidenceError, match=message):
            acquire_fixture_evidence(request, _catalog(), remaining_budget=2)
    else:
        with pytest.raises(P119EvidenceError, match=message):
            build_evidence_request(request_payload)


def test_evidence_rejects_contaminated_or_hidden_target_sources() -> None:
    request = build_evidence_request(_request())
    catalog = _catalog()
    catalog["source:metric"]["contaminated"] = True
    with pytest.raises(P119EvidenceError, match="contaminated_evidence_source"):
        acquire_fixture_evidence(request, catalog, remaining_budget=2)


def _request() -> dict[str, object]:
    return {
        "request_id": "req-1",
        "incident_id": "inc-1",
        "fixture_id": "local:fixture:checkout-api",
        "evidence_class": "metric_window",
        "source_ref": "source:metric",
        "budget_cost": 1,
        "value_of_information": 0.25,
    }


def _catalog() -> dict[str, dict[str, object]]:
    return {
        "source:metric": {
            "evidence_id": "ev-metric",
            "fixture_id": "local:fixture:checkout-api",
            "evidence_class": "metric_window",
            "source_hash": "sha256:" + "b" * 64,
            "value": {"p95_latency_ms": 900},
        }
    }
