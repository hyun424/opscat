from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p176_evidence import (
    P176EvidenceError,
    append_evidence_record,
    validate_evidence_chain,
    validate_evidence_record,
)


def _record(*, ledger_name: str = "agent_visible", source_class: str = "metrics", summary: dict[str, object] | None = None) -> dict[str, object]:
    return append_evidence_record(
        previous=None,
        ledger_name=ledger_name,
        source_class=source_class,
        source_id="checkout/prometheus/pool-wait",
        observed_at="2026-01-01T00:00:00Z",
        received_at="2026-01-01T00:02:00Z",
        freshness_bound_seconds=300,
        content_hash=stable_hash({"sample": source_class}),
        redaction_receipt_hash=stable_hash({"redacted": source_class}),
        summary=summary or {"signal": "pool_wait_high", "value_bucket": "p95_gt_2s"},
        evaluator_context_hash=stable_hash({"truth": "sealed"}) if ledger_name == "evaluator_only" else None,
    )


def test_agent_visible_and_evaluator_only_ledgers_chain_independently() -> None:
    agent_first = _record(ledger_name="agent_visible")
    agent_second = append_evidence_record(
        previous=agent_first,
        ledger_name="agent_visible",
        source_class="logs",
        source_id="checkout/loki/errors",
        observed_at="2026-01-01T00:01:00Z",
        received_at="2026-01-01T00:02:30Z",
        freshness_bound_seconds=300,
        content_hash=stable_hash({"sample": "logs"}),
        redaction_receipt_hash=stable_hash({"redacted": "logs"}),
        summary={"signal": "timeout_errors_present"},
    )
    agent_third = append_evidence_record(
        previous=agent_second,
        ledger_name="agent_visible",
        source_class="traces",
        source_id="checkout/trace/latency",
        observed_at="2026-01-01T00:02:00Z",
        received_at="2026-01-01T00:03:00Z",
        freshness_bound_seconds=300,
        content_hash=stable_hash({"sample": "traces"}),
        redaction_receipt_hash=stable_hash({"redacted": "traces"}),
        summary={"signal": "downstream_latency_bucket_high"},
    )
    evaluator_first = _record(ledger_name="evaluator_only")

    assert agent_first["sequence"] == 1
    assert agent_second["sequence"] == 2
    assert agent_second["previous_record_hash"] == agent_first["record_hash"]
    assert evaluator_first["sequence"] == 1
    assert evaluator_first["previous_record_hash"] == ""

    assert agent_third["sequence"] == 3
    validate_evidence_chain([agent_first, agent_second, agent_third], ledger_name="agent_visible")
    validate_evidence_chain([evaluator_first], ledger_name="evaluator_only")

    confused = deepcopy(agent_second)
    confused["ledger_name"] = "evaluator_only"
    confused["record_hash"] = stable_hash({key: value for key, value in confused.items() if key != "record_hash"})
    with pytest.raises(P176EvidenceError, match="ledger_predecessor_confusion"):
        validate_evidence_record(confused, previous=agent_first, ledger_name="evaluator_only")


def test_evidence_schema_allowlist_freshness_and_redaction_fail_closed() -> None:
    for source_class in (
        "metrics",
        "logs",
        "traces",
        "deploy_history",
        "host_state",
        "container_state",
        "topology",
        "dependency_health",
    ):
        validate_evidence_record(_record(source_class=source_class))

    with pytest.raises(P176EvidenceError, match="unsupported_source_class"):
        _record(source_class="tickets")
    with pytest.raises(P176EvidenceError, match="stale_evidence"):
        append_evidence_record(
            previous=None,
            ledger_name="agent_visible",
            source_class="metrics",
            source_id="checkout/prometheus/pool-wait",
            observed_at="2026-01-01T00:00:00Z",
            received_at="2026-01-01T00:10:01Z",
            freshness_bound_seconds=300,
            content_hash=stable_hash({"sample": "metrics"}),
            redaction_receipt_hash=stable_hash({"redacted": "metrics"}),
            summary={"signal": "pool_wait_high"},
        )
    with pytest.raises(P176EvidenceError, match="redaction_required"):
        append_evidence_record(
            previous=None,
            ledger_name="agent_visible",
            source_class="metrics",
            source_id="checkout/prometheus/pool-wait",
            observed_at="2026-01-01T00:00:00Z",
            received_at="2026-01-01T00:01:00Z",
            freshness_bound_seconds=300,
            content_hash=stable_hash({"sample": "metrics"}),
            redaction_receipt_hash="",
            summary={"signal": "pool_wait_high"},
        )


def test_agent_visible_records_reject_urls_secrets_raw_payload_and_truth_fields() -> None:
    forbidden_cases: list[dict[str, Any]] = [
        {"signal": "see http://internal.example/trace/1"},
        {"token": "[REDACTED]"},
        {"raw_payload": {"line": "redacted but still raw"}},
        {"ground_truth": "db_pool_exhaustion"},
        {"nested": {"root_cause_truth": "worker_crash"}},
    ]
    for summary in forbidden_cases:
        with pytest.raises(P176EvidenceError):
            _record(summary=summary)


def test_replay_forgery_sequence_and_cross_ledger_confusion_are_detected() -> None:
    first = _record()
    second = append_evidence_record(
        previous=first,
        ledger_name="agent_visible",
        source_class="traces",
        source_id="checkout/trace/span",
        observed_at="2026-01-01T00:01:00Z",
        received_at="2026-01-01T00:02:00Z",
        freshness_bound_seconds=300,
        content_hash=stable_hash({"sample": "traces"}),
        redaction_receipt_hash=stable_hash({"redacted": "traces"}),
        summary={"signal": "checkout_to_db_latency_bucket_high"},
    )
    forged = deepcopy(second)
    forged["summary"] = {"signal": "changed_after_hash"}
    with pytest.raises(P176EvidenceError, match="record_hash_invalid"):
        validate_evidence_record(forged, previous=first, ledger_name="agent_visible")

    replayed = [first, second, second]
    with pytest.raises(P176EvidenceError, match="sequence_mismatch"):
        validate_evidence_chain(replayed, ledger_name="agent_visible")

    evaluator_first = _record(ledger_name="evaluator_only")
    with pytest.raises(P176EvidenceError, match="ledger_predecessor_confusion"):
        append_evidence_record(
            previous=evaluator_first,
            ledger_name="agent_visible",
            source_class="metrics",
            source_id="checkout/prometheus/pool-wait",
            observed_at="2026-01-01T00:03:00Z",
            received_at="2026-01-01T00:04:00Z",
            freshness_bound_seconds=300,
            content_hash=stable_hash({"sample": "metrics2"}),
            redaction_receipt_hash=stable_hash({"redacted": "metrics2"}),
            summary={"signal": "pool_wait_high"},
        )


def test_complete_chain_rejects_empty_missing_sources_and_non_finite_values() -> None:
    with pytest.raises(P176EvidenceError, match="empty"):
        validate_evidence_chain([], ledger_name="agent_visible")

    one = _record()
    with pytest.raises(P176EvidenceError, match="coverage"):
        validate_evidence_chain([one], ledger_name="agent_visible", require_all_source_classes=True)

    with pytest.raises(P176EvidenceError, match="non_finite"):
        _record(summary={"value": math.nan})
