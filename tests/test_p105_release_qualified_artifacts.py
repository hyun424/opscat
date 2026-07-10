from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from app.services.proactive_risk_sentinel import ProactiveRiskSentinel, RiskSignal, load_proactive_fixtures

RELEASE_BENCHMARK = Path("evals/proactive/forecast/p105_release_benchmark_rows.json")
P24_WINDOWS = Path("evals/proactive/seed/risk_windows.json")

REQUIRED_MANIFESTS = {
    "rows",
    "sources",
    "source_availability_preflight",
    "private_label_ledger",
    "partitions",
    "coverage",
    "p24_parity",
    "benchmark",
    "review",
}
EXACT_FLOORS = {
    "held_out": {
        "evaluated_count": 30,
        "non_abstained_count": 24,
        "positive_count": 6,
        "incident_group_count": 4,
        "service_day_count": 2.0,
    },
    "real_derived_shadow": {
        "evaluated_count": 20,
        "non_abstained_count": 16,
        "positive_count": 4,
        "incident_group_count": 3,
        "service_day_count": 1.0,
    },
}
ZERO_AUTHORITY = {
    "auth_enabled": False,
    "production_mutation_enabled": False,
    "action_authority": False,
    "remediation_execution_enabled": False,
    "default_external_model_calls": 0,
}


def _api() -> Any:
    return importlib.import_module("app.services.failure_forecast_engine")


def _payload() -> dict[str, Any]:
    return json.loads(RELEASE_BENCHMARK.read_text(encoding="utf-8"))


def _write_payload(tmp_path: Path, payload: dict[str, Any], name: str) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _validate_artifact(path: Path) -> dict[str, Any]:
    validator = getattr(_api(), "validate_p105_release_qualified_artifact", None)
    if validator is None:
        pytest.fail("G006 artifact validator missing: expose validate_p105_release_qualified_artifact.", pytrace=False)
    return validator(path)


def test_locked_smoke_artifact_cannot_unlock_p106() -> None:
    report = _api().run_p105_benchmark(RELEASE_BENCHMARK)

    assert report["release_gate"]["qualification_mode"] == "smoke_only_missing_mode"
    assert report["release_gate"]["release_qualified"] is False
    assert report["release_gate"]["p106_unlocked"] is False
    assert report["release_gate"]["qualification_floors"]["pass"] is False


def test_qualified_artifact_references_every_required_manifest_with_stable_content_hash(tmp_path: Path) -> None:
    payload = _payload()
    payload["mode"] = "release_qualified"
    path = _write_payload(tmp_path, payload, "candidate.json")

    result = _validate_artifact(path)

    manifests = result["artifact_manifests"]
    assert set(manifests) == REQUIRED_MANIFESTS
    for name, manifest in manifests.items():
        assert manifest["path"]
        assert len(manifest["sha256"]) == 64, name
        assert manifest["referenced_by_benchmark_payload"] is True
    assert result["release_gate"]["release_qualified"] is False
    assert result["release_gate"]["p106_unlocked"] is False


def test_qualified_artifact_requires_exact_floors_metrics_and_p106_gate_rows(tmp_path: Path) -> None:
    payload = _payload()
    payload["mode"] = "release_qualified"
    path = _write_payload(tmp_path, payload, "floors.json")

    result = _validate_artifact(path)

    assert result["qualification_floors"]["floor_contract_version"] == "p105-g006"
    for family, partitions in result["qualification_floors"]["families"].items():
        assert family in {"database", "deploy", "queue"}
        for partition, expected in EXACT_FLOORS.items():
            for metric, minimum in expected.items():
                assert partitions[partition][metric]["minimum"] == minimum
    assert result["p106_gate_rows"]["required"] == [
        "held_out_calibration",
        "per_family_release_metrics",
        "global_release_metrics",
        "real_derived_transfer",
        "safety_boundary",
    ]
    assert result["release_gate"]["release_qualified"] is False
    assert result["release_gate"]["p106_unlocked"] is False


def test_p24_parity_partition_coverage_and_incident_isolation(tmp_path: Path) -> None:
    payload = _payload()
    payload["mode"] = "release_qualified"
    path = _write_payload(tmp_path, payload, "parity.json")

    result = _validate_artifact(path)

    parity = result["p24_parity_manifest"]
    assert parity["authority"] == {
        "risk_signal": "app.services.proactive_risk_sentinel.RiskSignal",
        "risk_forecast": "app.services.proactive_risk_sentinel.RiskForecast",
    }
    assert parity["no_fallback_policy"] == "fail_closed_per_row"
    assert parity["denominator_alignment_status"] == "exact"
    for row in parity["rows"]:
        assert {
            "source_window_id",
            "p24_input_hash",
            "risk_signal_output_hash",
            "risk_forecast_output_hash",
            "denominator_alignment_status",
        } <= set(row)
        assert row["denominator_alignment_status"] == "exact"

    partitions = result["partition_manifest"]
    assert partitions["assignment_inputs_exclude"] == [
        "label_positive",
        "p24_score",
        "p105_score",
        "lead_time_success",
        "false_alert_status",
        "safety_result",
        "p106_gate_status",
    ]
    assert partitions["incident_group_isolation"]["pass"] is True

    coverage = result["coverage_manifest"]
    assert coverage["false_alert_denominator_method"] == "merged_interval_union"
    assert coverage["union_scope_keys"] == ["split_id", "family", "service", "source_system"]


def test_exact_no_fallback_per_row_p24_parity_uses_current_p24_behavior(tmp_path: Path) -> None:
    payload = _payload()
    payload["mode"] = "release_qualified"
    path = _write_payload(tmp_path, payload, "p24-no-fallback.json")

    result = _validate_artifact(path)
    windows_by_id = {window.id: window for window in load_proactive_fixtures(P24_WINDOWS)}
    sentinel = ProactiveRiskSentinel()

    for row in result["p24_parity_manifest"]["rows"]:
        window = windows_by_id[row["source_window_id"]]
        signal = RiskSignal.from_window(window)
        forecast = sentinel._forecast(signal).to_dict()
        assert row["risk_signal_output_hash"] == result["hashes"]["risk_signals"][window.id]
        assert row["risk_forecast_output_hash"] == result["hashes"]["risk_forecasts"][forecast["forecast_id"]]
        assert row["fallback_used"] is False


def test_missing_original_p24_input_hash_fails_closed_instead_of_using_seed_window_fallback(tmp_path: Path) -> None:
    payload = _payload()
    payload["mode"] = "release_qualified"
    payload["p24_parity_manifest"] = {
        "rows": [
            {
                "source_window_id": "nonexistent-window",
                "p24_input_hash": None,
                "fallback_source_window_id": "pre-db-pool-wait-rising",
            }
        ]
    }
    path = _write_payload(tmp_path, payload, "p24-fallback-attempt.json")

    result = _validate_artifact(path)

    assert "p24_parity_source_window_unreconstructable" in result["release_gate"]["validation_error_codes"]
    assert "p24_parity_fallback_attempt" in result["release_gate"]["validation_error_codes"]
    assert result["release_gate"]["release_qualified"] is False
    assert result["release_gate"]["p106_unlocked"] is False


def test_private_label_ledger_tamper_or_public_label_leak_fails_closed(tmp_path: Path) -> None:
    payload = _payload()
    payload["mode"] = "release_qualified"
    payload["private_scorer_label_ledger"] = {
        "records": [{"row_id": payload["rows"][0]["row_id"], "label_hash": "tampered"}]
    }
    payload["rows"][0]["public_features"]["label_positive"] = True
    path = _write_payload(tmp_path, payload, "label-tamper.json")

    result = _validate_artifact(path)

    assert "private_label_ledger_tamper" in result["release_gate"]["validation_error_codes"]
    assert "scorer_label_leakage" in result["release_gate"]["validation_error_codes"]
    assert result["release_gate"]["release_qualified"] is False
    assert result["release_gate"]["p106_unlocked"] is False


def test_nonzero_authority_counter_blocks_qualified_artifact(tmp_path: Path) -> None:
    payload = _payload()
    payload["mode"] = "release_qualified"
    payload["authority"] = copy.deepcopy(ZERO_AUTHORITY)
    payload["authority"]["action_authority"] = True
    path = _write_payload(tmp_path, payload, "authority.json")

    result = _validate_artifact(path)

    assert result["authority"] != ZERO_AUTHORITY
    assert "nonzero_authority_counter" in result["release_gate"]["validation_error_codes"]
    assert result["release_gate"]["release_qualified"] is False
    assert result["release_gate"]["p106_unlocked"] is False
