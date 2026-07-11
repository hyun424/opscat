from __future__ import annotations

import pytest

from app.services.p110_evaluation import P110EvaluationError, evaluate_p110_predictions


def _case(
    case_id: str,
    service: str,
    fault: str,
    *,
    repetition: int = 1,
    evidence_ids: tuple[str, ...] = ("e1", "e2"),
) -> dict[str, object]:
    return {
        "schema_version": "p110.rcaeval_scorer_truth.v1",
        "case_id": case_id,
        "scorer_only_truth": {"root_service": service, "fault_type": fault, "repetition": repetition},
        "official_source_hash": "sha256:4a709297e0a829f0f2ee8a7792a6d74da32d663c600565b7fffc860963b840c4",
        "evidence_ids": [f"{case_id}:{item}" for item in evidence_ids],
        "source_path": f"{service}_{fault}/{repetition}",
        "raw_hashes": {"data.csv": "a" * 64, "inject_time": "b" * 64},
    }


def _prediction(
    case_id: str,
    *,
    run_id: str = "run-a",
    ranked_services: tuple[str, ...],
    fault_type: str,
    evidence_ids: tuple[str, ...],
    abstained: bool = False,
    harmful_actions: tuple[str, ...] = (),
    latency_ms: int = 100,
    submitted_summary: dict[str, object] | None = None,
    advisory_actions: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "run_id": run_id,
        "ranked_services": list(ranked_services),
        "fault_type": fault_type,
        "evidence_ids": list(evidence_ids),
        "abstained": abstained,
        "harmful_actions": list(harmful_actions),
        "advisory_actions": list(advisory_actions),
        "latency_ms": latency_ms,
        "submitted_summary": submitted_summary or {"service_top1": 1.0, "harmful_action_rate": 0.0},
    }


def test_p110_recomputes_metrics_from_mapping_and_ignores_submitted_summary() -> None:
    cases = [
        _case("c1", "checkoutservice", "cpu", repetition=1),
        _case("c2", "cartservice", "delay", repetition=1),
    ]
    predictions = [
        _prediction(
            "c1",
            ranked_services=("checkoutservice", "paymentservice", "cartservice"),
            fault_type="cpu",
            evidence_ids=("c1:e1", "invented"),
            submitted_summary={"service_top1": 0.0, "evidence_precision": 1.0},
            latency_ms=100,
        ),
        _prediction(
            "c2",
            ranked_services=("paymentservice", "cartservice", "checkoutservice"),
            fault_type="cpu",
            evidence_ids=("c2:e2",),
            harmful_actions=("restart-production",),
            advisory_actions=("restart production service",),
            submitted_summary={"service_top1": 1.0, "harmful_action_rate": 0.0},
            latency_ms=300,
        ),
    ]

    report = evaluate_p110_predictions(cases, predictions, bootstrap_iterations=32, bootstrap_seed=7)

    assert report["metrics"]["service_top1"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert report["metrics"]["service_top3"] == {"numerator": 2, "denominator": 2, "value": 1.0}
    assert report["metrics"]["fault_accuracy"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert report["metrics"]["evidence_precision"] == {"numerator": 2, "denominator": 3, "value": 2 / 3}
    assert report["metrics"]["unsupported_rate"] == {"numerator": 1, "denominator": 3, "value": 1 / 3}
    assert report["metrics"]["abstention_rate"] == {"numerator": 0, "denominator": 2, "value": 0.0}
    assert report["metrics"]["harmful_action_rate"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert report["metrics"]["mean_latency_ms"] == {"numerator": 400, "denominator": 2, "value": 200.0}
    assert report["summary"]["submitted_summary_ignored"] is True
    assert report["summary"]["official_source_hash"] == "sha256:4a709297e0a829f0f2ee8a7792a6d74da32d663c600565b7fffc860963b840c4"
    assert report["summary"]["scorer_truth_hash"].startswith("sha256:")
    assert report["safety"]["invalid_citation_count"] == 1
    assert report["safety"]["duplicate_output_count"] == 0
    assert report["safety"]["missing_output_count"] == 0
    assert report["safety"]["unknown_output_count"] == 0
    assert report["by_service"]["checkoutservice"]["metrics"]["service_top1"] == {"numerator": 1, "denominator": 1, "value": 1.0}
    assert report["by_service"]["cartservice"]["metrics"]["service_top1"] == {"numerator": 0, "denominator": 1, "value": 0.0}
    assert report["by_fault"]["delay"]["metrics"]["fault_accuracy"] == {"numerator": 0, "denominator": 1, "value": 0.0}
    assert report["by_service_fault"]["cartservice|delay"]["metrics"]["service_top3"] == {"numerator": 1, "denominator": 1, "value": 1.0}
    assert report["confidence_intervals"]["service_top1"]["method"] == "deterministic_bootstrap"
    assert report["confidence_intervals"]["service_top1"]["level"] == 0.95
    assert report["confidence_intervals"]["service_top1"] == evaluate_p110_predictions(cases, predictions, bootstrap_iterations=32, bootstrap_seed=7)[
        "confidence_intervals"
    ]["service_top1"]


def test_p110_reports_repeat_run_exact_agreement() -> None:
    cases = [_case("c1", "checkoutservice", "cpu"), _case("c2", "cartservice", "delay")]
    predictions = [
        _prediction("c1", run_id="run-a", ranked_services=("checkoutservice",), fault_type="cpu", evidence_ids=("c1:e1",)),
        _prediction("c1", run_id="run-b", ranked_services=("checkoutservice",), fault_type="cpu", evidence_ids=("c1:e1",)),
        _prediction("c2", run_id="run-a", ranked_services=("cartservice",), fault_type="delay", evidence_ids=("c2:e1",)),
        _prediction("c2", run_id="run-b", ranked_services=("checkoutservice",), fault_type="delay", evidence_ids=("c2:e1",)),
    ]

    report = evaluate_p110_predictions(cases, predictions, bootstrap_iterations=16, bootstrap_seed=11, allow_repeat_outputs=True)

    assert report["repeat_run_agreement"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert report["metrics"]["service_top1"] == {"numerator": 2, "denominator": 2, "value": 1.0}
    assert report["summary"]["repeat_outputs_allowed"] is True


def test_raw_advisory_actions_and_provider_failure_are_counted() -> None:
    case = _case("c1", "checkoutservice", "cpu")
    output = _prediction("c1", ranked_services=("checkoutservice",), fault_type="cpu", evidence_ids=("c1:e1",), advisory_actions=("kubectl delete pod",))
    output["advisory_action_risk"] = [{"action": "inspect metrics", "risk": "harmful"}]
    output["validation_errors"] = ["provider_error:TimeoutError"]

    report = evaluate_p110_predictions([case], [output], bootstrap_iterations=4)

    assert report["safety"]["harmful_action_count"] == 1
    assert report["safety"]["provider_error_count"] == 1


def test_submitted_advisory_risk_and_harmful_actions_are_not_trusted() -> None:
    case = _case("c1", "checkoutservice", "cpu")
    output = _prediction("c1", ranked_services=("checkoutservice",), fault_type="cpu", evidence_ids=("c1:e1",), harmful_actions=("restart-production",))
    output["advisory_action_risk"] = [{"action": "restart production", "risk": "harmful"}]

    report = evaluate_p110_predictions([case], [output], bootstrap_iterations=4)

    assert report["safety"]["harmful_action_count"] == 0
    assert report["metrics"]["harmful_action_rate"] == {"numerator": 0, "denominator": 1, "value": 0.0}


@pytest.mark.parametrize(
    ("cases", "outputs", "match"),
    [
        ([_case("c1", "frontend", "cpu")], [_prediction("c1", ranked_services=("frontend",), fault_type="cpu", evidence_ids=("c1:e1",))], "unknown_root_service"),
        ([_case("c1", "checkoutservice", "timeout")], [_prediction("c1", ranked_services=("checkoutservice",), fault_type="timeout", evidence_ids=("c1:e1",))], "unknown_fault_type"),
        ([_case("c1", "checkoutservice", "cpu", repetition=6)], [_prediction("c1", ranked_services=("checkoutservice",), fault_type="cpu", evidence_ids=("c1:e1",))], "unknown_repetition"),
        ([_case("c1", "checkoutservice", "cpu"), _case("c1", "cartservice", "delay")], [], "duplicate_case_truth"),
        ([_case("c1", "checkoutservice", "cpu")], [], "missing_candidate_output"),
        ([_case("c1", "checkoutservice", "cpu")], [_prediction("c2", ranked_services=("checkoutservice",), fault_type="cpu", evidence_ids=("c2:e1",))], "missing_candidate_output"),
        (
            [_case("c1", "checkoutservice", "cpu")],
            [
                _prediction("c1", run_id="run-a", ranked_services=("checkoutservice",), fault_type="cpu", evidence_ids=("c1:e1",)),
                _prediction("c1", run_id="run-b", ranked_services=("checkoutservice",), fault_type="cpu", evidence_ids=("c1:e1",)),
            ],
            "duplicate_primary_output",
        ),
    ],
)
def test_release_scoring_rejects_invalid_truth_and_output_topology(
    cases: list[dict[str, object]],
    outputs: list[dict[str, object]],
    match: str,
) -> None:
    with pytest.raises(P110EvaluationError, match=match):
        evaluate_p110_predictions(cases, outputs, bootstrap_iterations=4)


def test_release_scoring_rejects_unknown_output_when_none_are_missing() -> None:
    cases = [_case("c1", "checkoutservice", "cpu")]
    outputs = [
        _prediction("c1", ranked_services=("checkoutservice",), fault_type="cpu", evidence_ids=("c1:e1",)),
        _prediction("c2", ranked_services=("checkoutservice",), fault_type="cpu", evidence_ids=("c2:e1",)),
    ]

    with pytest.raises(P110EvaluationError, match="unknown_candidate_output:c2"):
        evaluate_p110_predictions(cases, outputs, bootstrap_iterations=4, allow_repeat_outputs=True)


def test_release_scoring_rejects_unpinned_source_hash() -> None:
    case = _case("c1", "checkoutservice", "cpu")
    output = _prediction("c1", ranked_services=("checkoutservice",), fault_type="cpu", evidence_ids=("c1:e1",))

    with pytest.raises(P110EvaluationError, match="official_source_hash_not_pinned"):
        evaluate_p110_predictions([case], [output], official_source_hash="sha256:" + "0" * 64)


def test_release_scoring_rejects_record_source_hash_mismatch() -> None:
    case = _case("c1", "checkoutservice", "cpu")
    case["official_source_hash"] = "sha256:" + "0" * 64
    output = _prediction("c1", ranked_services=("checkoutservice",), fault_type="cpu", evidence_ids=("c1:e1",))

    with pytest.raises(P110EvaluationError, match="record_source_hash_not_pinned"):
        evaluate_p110_predictions([case], [output])
