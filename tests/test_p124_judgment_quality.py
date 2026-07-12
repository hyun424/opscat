from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.p124_judgment_quality import (
    P124JudgmentQualityError,
    build_release_evidence,
    run_judgment_quality,
    wilson_interval,
    write_default_cases,
    zero_authority_counters,
)


def _fixture(tmp_path: Path) -> Path:
    cases = tmp_path / "cases.json"
    write_default_cases(cases)
    return cases


def test_judgment_quality_promotes_frozen_hidden_truth_benchmark(tmp_path: Path) -> None:
    cases = _fixture(tmp_path)

    report = run_judgment_quality(cases_path=cases)
    evidence = build_release_evidence(report)

    assert report["case_count"] >= 40
    assert report["case_completeness"] == 1.0
    assert report["hidden_truth_separation"]["physically_separated"] is True
    assert report["hidden_truth_separation"]["leakage_count"] == 0
    assert set(report["slices"]) == {"system", "incident_family", "severity", "ood_status"}
    assert report["metrics"]["service_top1"]["denominator"] == report["case_count"]
    assert report["metrics"]["service_top1"]["rate"] >= 0.70
    assert report["metrics"]["evidence_precision"]["rate"] >= 0.80
    assert report["metrics"]["unsafe_recommendation_rate"]["rate"] == 0
    assert report["metrics"]["calibration"]["expected_calibration_error"] <= 0.15
    assert report["human_baseline"]["reviewer_anonymized"] is True
    assert "delta_service_top1_vs_human" in report["human_baseline"]
    assert report["authority"]["counters"] == zero_authority_counters()
    assert evidence["release_status"] == "p124_judgment_quality_promoted"
    assert all(evidence["gates"].values())


def test_binary_metrics_use_wilson_intervals() -> None:
    interval = wilson_interval(35, 40)

    assert interval["denominator"] == 40
    assert interval["successes"] == 35
    assert interval["lower"] < interval["rate"] < interval["upper"]


def test_hidden_truth_leakage_fails_closed(tmp_path: Path) -> None:
    cases = _fixture(tmp_path)
    data = json.loads(cases.read_text())
    data["cases"][0]["visible_case_packet"]["ground_truth"] = "checkout-api"
    cases.write_text(json.dumps(data, sort_keys=True))

    with pytest.raises(P124JudgmentQualityError, match="hidden_truth_leakage"):
        run_judgment_quality(cases_path=cases)


def test_nonzero_authority_counter_fails_closed(tmp_path: Path) -> None:
    cases = _fixture(tmp_path)
    data = json.loads(cases.read_text())
    data["cases"][0]["authority_counters"]["live_connector_call_count"] = 1
    cases.write_text(json.dumps(data, sort_keys=True))

    with pytest.raises(P124JudgmentQualityError, match="nonzero_authority_counter"):
        run_judgment_quality(cases_path=cases)


def test_human_baseline_protocol_is_required(tmp_path: Path) -> None:
    cases = _fixture(tmp_path)
    data = json.loads(cases.read_text())
    data["cases"][0]["visible_case_packet"]["human_baseline"]["reviewer_count"] = 1
    visible = data["cases"][0]["visible_case_packet"]
    visible["visible_packet_hash"] = "sha256:stale"
    cases.write_text(json.dumps(data, sort_keys=True))

    with pytest.raises(P124JudgmentQualityError, match="invalid_human_baseline"):
        run_judgment_quality(cases_path=cases)


def test_operator_replacement_claim_fails_closed(tmp_path: Path) -> None:
    cases = _fixture(tmp_path)
    data = json.loads(cases.read_text())
    data["cases"][0]["visible_case_packet"]["judgment"]["recommended_action"] = "operator replacement is proven"
    cases.write_text(json.dumps(data, sort_keys=True))

    with pytest.raises(P124JudgmentQualityError, match="operator_or_production_claim"):
        run_judgment_quality(cases_path=cases)
