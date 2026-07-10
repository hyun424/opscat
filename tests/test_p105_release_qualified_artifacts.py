from __future__ import annotations

import copy
import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.services.proactive_risk_sentinel import ProactiveRiskSentinel, RiskSignal, load_proactive_fixtures

RELEASE_BENCHMARK = Path("evals/proactive/forecast/p105_release_benchmark_rows.json")
P24_WINDOWS = Path("evals/proactive/seed/risk_windows.json")
P32_REPLAY = Path("evals/telemetry/replay/p32_replay_pack.json")
P41_SOURCES = Path("evals/real_datasets/raw/p41_sources.json")
MATERIALIZER_SCRIPT = Path("scripts/materialize_p105_release_evidence.py")

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
OUTPUT_MANIFESTS = {
    "source_availability_preflight": "p105-source-availability-preflight.json",
    "private_label_ledger": "p105-private-scorer-label-ledger.json",
    "partitions": "p105-partitions.json",
    "coverage": "p105-coverage.json",
    "p24_parity": "p105-p24-parity.json",
    "benchmark": "p105-release-qualified-benchmark.json",
    "review": "p105-review.json",
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


def _reviewed_p44_manifest(tmp_path: Path) -> Path:
    records_path = tmp_path / "reviewed-p44-records.jsonl"
    records = []
    for family in ("database", "deploy", "queue"):
        for partition, count, positives in (("held_out", 30, 6), ("real_derived_shadow", 20, 4)):
            for index in range(count):
                records.append(
                    {
                        "record_id": f"{family}-{partition}-{index:03d}",
                        "family": family,
                        "partition": partition,
                        "source_window_id": f"p44-window-{family}-{partition}-{index:03d}",
                        "public_features": {"metric": f"{family}.saturation", "value": 100 + index},
                        "private_label": {
                            "label_positive": index < positives,
                            "label_incident_id": f"inc-{family}-{partition}-{index:03d}" if index < positives else None,
                            "incident_group_id": f"group-{family}-{partition}-{index % max(positives, 1):03d}",
                            "lead_time_label_minutes": 60 if index < positives else None,
                        },
                        "p24_input": {
                            "window_id": f"p44-window-{family}-{partition}-{index:03d}",
                            "family": family,
                            "value": 100 + index,
                        },
                    }
                )
    records_path.write_text("\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n", encoding="utf-8")
    manifest_path = tmp_path / "p44-reviewed-local-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "p105.reviewed_p44_local_manifest.v2",
                "review_redaction_status": "reviewed_redacted",
                "sources": [
                    {
                        "source_id": "p44:test:reviewed-local",
                        "family": "multi",
                        "local_materialized_path": str(records_path),
                        "local_source_hash": __import__("hashlib").sha256(records_path.read_bytes()).hexdigest(),
                        "record_count": len(records),
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _materialize_reviewed_local(tmp_path: Path) -> Path:
    output_dir = tmp_path / "qualified"
    completed = subprocess.run(
        [
            sys.executable,
            str(MATERIALIZER_SCRIPT),
            "--p32-replay",
            str(P32_REPLAY),
            "--p41-sources",
            str(P41_SOURCES),
            "--p44-reviewed-local-manifest",
            str(_reviewed_p44_manifest(tmp_path)),
            "--p44-mode",
            "reviewed-local",
            "--output-dir",
            str(output_dir),
            "--mode",
            "release_qualified",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return output_dir


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


def test_every_qualified_row_has_reconstructable_p24_parity_without_seed_fallback(tmp_path: Path) -> None:
    output_dir = _materialize_reviewed_local(tmp_path)
    rows_path = output_dir / "p105-release-qualified-rows.json"

    result = _validate_artifact(rows_path)
    rows = json.loads(rows_path.read_text(encoding="utf-8"))["rows"]
    parity_by_row_id = {row["row_id"]: row for row in result["p24_parity_manifest"]["rows"]}

    assert set(parity_by_row_id) == {row["row_id"] for row in rows}
    for row in rows:
        parity = parity_by_row_id[row["row_id"]]
        assert parity["source_window_id"] == row["source_window_id"]
        assert parity["p24_input_hash"] == row["p24_input_hash"]
        assert parity["denominator_alignment_status"] == "exact"
        assert parity["fallback_used"] is False
        assert "fallback_source_window_id" not in parity


def test_materializer_output_is_self_benchmarkable_with_private_ledger_join_and_no_public_label_leakage(tmp_path: Path) -> None:
    output_dir = _materialize_reviewed_local(tmp_path)
    rows_path = output_dir / "p105-release-qualified-rows.json"
    payload = json.loads(rows_path.read_text(encoding="utf-8"))
    public_rows_json = json.dumps(payload["rows"], sort_keys=True)

    assert "scorer_labels" not in public_rows_json
    assert "label_positive" not in public_rows_json
    assert payload["private_scorer_label_ledger_path"] == "p105-private-scorer-label-ledger.json"

    report = _api().run_p105_benchmark(rows_path)

    assert report["private_ledger_join"]["source"] == "p105-private-scorer-label-ledger.json"
    assert report["private_ledger_join"]["joined_row_count"] == len(payload["rows"])
    assert report["release_gate"]["release_qualified"] is True
    assert report["release_gate"]["p106_unlocked"] is True


def test_validator_reports_real_gate_outcome_instead_of_forcing_false(tmp_path: Path) -> None:
    output_dir = _materialize_reviewed_local(tmp_path)
    rows_path = output_dir / "p105-release-qualified-rows.json"

    benchmark_report = _api().run_p105_benchmark(rows_path)
    validation = _validate_artifact(rows_path)

    assert benchmark_report["release_gate"]["release_qualified"] is True
    assert benchmark_report["release_gate"]["p106_unlocked"] is True
    assert validation["release_gate"]["release_qualified"] is True
    assert validation["release_gate"]["p106_unlocked"] is True
