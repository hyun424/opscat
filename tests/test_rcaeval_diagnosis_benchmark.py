from __future__ import annotations

from pathlib import Path

from app.services.rcaeval_adapter import load_rcaeval_cases
from app.services.rcaeval_diagnosis_benchmark import (
    DiagnosisPrediction,
    evaluate_diagnosis_predictions,
)

FIXTURE_ROOT = Path("tests/fixtures/p109/rcaeval")


def test_diagnosis_benchmark_scores_exact_numerator_denominator_and_safety_metrics() -> None:
    cases = load_rcaeval_cases(FIXTURE_ROOT / "cases")
    report = evaluate_diagnosis_predictions(
        cases,
        [
            DiagnosisPrediction(
                case_id="checkout-001",
                ranked_services=("checkout", "payments", "inventory"),
                fault_type="timeout",
                evidence_refs=("logs.jsonl:1", "metrics.csv:1"),
                abstain=False,
                latency_ms=1250,
                tool_call_count=2,
            )
        ],
    )
    payload = report.to_dict()

    assert payload["summary"]["case_count"] == 1
    assert payload["summary"]["truth_eligible_case_count"] == 1
    assert payload["summary"]["release_qualified"] is False
    assert payload["metrics"]["service_top1"] == {"numerator": 1, "denominator": 1, "value": 1.0}
    assert payload["metrics"]["service_top3"] == {"numerator": 1, "denominator": 1, "value": 1.0}
    assert payload["metrics"]["fault_type_accuracy"] == {"numerator": 1, "denominator": 1, "value": 1.0}
    assert payload["metrics"]["evidence_precision"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert payload["metrics"]["unsupported_claim_rate"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert payload["metrics"]["abstention_accuracy"] == {"numerator": 1, "denominator": 1, "value": 1.0}
    assert payload["metrics"]["mean_latency_ms"] == {"numerator": 1250, "denominator": 1, "value": 1250.0}
    assert payload["metrics"]["mean_tool_call_count"] == {"numerator": 2, "denominator": 1, "value": 2.0}
    assert payload["by_cell"][0]["dataset"] == "rcaeval"
    assert payload["by_cell"][0]["system_id"] == "checkout-001"
    assert payload["by_cell"][0]["fault_family"] == "timeout"
    assert payload["by_cell"][0]["metrics"]["service_top1"]["denominator"] == 1


def test_truthless_simple_data_is_unevaluable_smoke_and_never_release_qualified() -> None:
    cases = load_rcaeval_cases(FIXTURE_ROOT / "simple_data")
    report = evaluate_diagnosis_predictions(
        cases,
        [
            DiagnosisPrediction(
                case_id="simple_data",
                ranked_services=("inventory",),
                fault_type="cpu",
                evidence_refs=("simple_data.csv:1",),
                abstain=True,
                latency_ms=100,
                tool_call_count=0,
            )
        ],
    )
    payload = report.to_dict()

    assert payload["summary"]["case_count"] == 1
    assert payload["summary"]["truth_eligible_case_count"] == 0
    assert payload["summary"]["real_telemetry_smoke_only"] is True
    assert payload["summary"]["release_qualified"] is False
    assert payload["metrics"]["service_top1"] == {"numerator": 0, "denominator": 0, "value": None}
    assert payload["metrics"]["fault_type_accuracy"] == {"numerator": 0, "denominator": 0, "value": None}
    assert payload["metrics"]["evidence_precision"] == {"numerator": 0, "denominator": 0, "value": None}
    assert payload["metrics"]["abstention_accuracy"] == {"numerator": 1, "denominator": 1, "value": 1.0}
    assert payload["by_cell"][0]["fault_family"] == "truth_unavailable"
    assert payload["by_cell"][0]["metrics"]["service_top1"]["value"] is None


def test_candidate_context_truth_leak_is_rejected_before_scoring() -> None:
    cases = load_rcaeval_cases(FIXTURE_ROOT / "cases")
    report = evaluate_diagnosis_predictions(
        cases,
        [
            DiagnosisPrediction(
                case_id="checkout-001",
                ranked_services=("checkout",),
                fault_type="timeout",
                evidence_refs=("logs.jsonl:1",),
                abstain=False,
                latency_ms=50,
                tool_call_count=0,
                candidate_context={"scorer_only_truth": {"root_service": "checkout"}},
            )
        ],
    )
    payload = report.to_dict()

    assert payload["summary"]["release_qualified"] is False
    assert payload["safety"]["candidate_context_truth_leak_count"] == 1
    assert payload["metrics"]["service_top1"]["denominator"] == 0
