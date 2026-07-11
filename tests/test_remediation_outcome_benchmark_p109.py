from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

FIXTURE = Path("tests/fixtures/p109/microremed/smoke_bundle.json")


def _api() -> Any:
    try:
        return importlib.import_module("app.services.remediation_outcome_benchmark_p109")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P109 RED: missing remediation outcome benchmark ({exc}).", pytrace=False)


def _get(value: Any, key: str, default: Any = None) -> Any:
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def test_benchmark_computes_exact_p109_numerators_denominators_and_outcomes() -> None:
    result = _api().run_remediation_outcome_benchmark(FIXTURE)
    payload = result.to_dict()

    assert payload["schema_version"] == "p109.remediation_outcome_benchmark.v1"
    assert payload["scored"] is True
    assert payload["release_evidence"] is False
    assert payload["release_trusted"] is False
    assert payload["fixture_results_smoke_only"] is True
    assert payload["eligible_run_count"] == 4
    assert payload["outcome_counts"] == {
        "verified_recovery": 1,
        "harmful": 1,
        "unnecessary": 1,
        "no_effect": 1,
        "unverified": 1,
    }
    assert payload["metrics"]["verified_recovery_rate"] == {
        "numerator": 1,
        "denominator": 4,
        "value": 0.25,
        "status": "scored",
    }
    assert payload["metrics"]["first_attempt_recovery_rate"] == {
        "numerator": 1,
        "denominator": 4,
        "value": 0.25,
        "status": "scored",
    }
    assert payload["metrics"]["attempt_success_rate"] == {
        "numerator": 1,
        "denominator": 4,
        "value": 0.25,
        "status": "scored",
    }
    assert payload["metrics"]["harmful_action_rate"] == {
        "numerator": 1,
        "denominator": 4,
        "value": 0.25,
        "status": "scored",
    }
    assert payload["metrics"]["unnecessary_action_rate"] == {
        "numerator": 1,
        "denominator": 4,
        "value": 0.25,
        "status": "scored",
    }
    assert payload["metrics"]["mean_attempts"] == {
        "numerator": 4,
        "denominator": 4,
        "value": 1.0,
        "status": "scored",
    }
    assert payload["metrics"]["mean_recovery_duration_seconds"] == {
        "numerator": 300,
        "denominator": 1,
        "value": 300.0,
        "status": "scored",
    }
    assert set(payload["by_system"]) == {"checkout", "billing", "search"}
    assert set(payload["by_fault_family"]) == {"deploy_config", "database", "natural_recovery", "cache"}
    assert set(payload["by_difficulty"]) == {"easy", "medium"}


def test_missing_or_zero_denominator_is_null_and_unevaluable(tmp_path: Path) -> None:
    source = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source["runs"] = [run for run in source["runs"] if run["run_id"] == "mr-unverified-recovery"]
    path = tmp_path / "unverified-only.json"
    path.write_text(json.dumps(source, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    payload = _api().run_remediation_outcome_benchmark(path).to_dict()

    assert payload["scored"] is False
    assert payload["eligible_run_count"] == 0
    for metric in payload["metrics"].values():
        assert metric["denominator"] == 0
        assert metric["value"] is None
        assert metric["status"] == "unevaluable"


def test_natural_recovery_noop_is_not_credited_to_intervention() -> None:
    payload = _api().run_remediation_outcome_benchmark(FIXTURE).to_dict()
    run = next(item for item in payload["runs"] if item["run_id"] == "mr-unnecessary-noop")

    assert run["outcome"] == "unnecessary"
    assert run["before_health"]["healthy"] is True
    assert run["non_noop_intervention"] is False
    assert run["credited_to_intervention"] is False


def test_matched_control_must_recover_after_minimum_effect_window_for_credit(tmp_path: Path) -> None:
    source = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source["runs"] = [run for run in source["runs"] if run["run_id"] == "mr-verified-recovery"]
    source["runs"][0]["matched_no_action_control"] = {
        "recovered": True,
        "recovery_duration_seconds": 280,
        "minimum_effect_window_seconds": 60,
    }
    path = tmp_path / "control-too-close.json"
    path.write_text(json.dumps(source, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    payload = _api().run_remediation_outcome_benchmark(path).to_dict()

    assert payload["runs"][0]["outcome"] == "no_effect"
    assert payload["metrics"]["verified_recovery_rate"]["numerator"] == 0
    assert payload["metrics"]["verified_recovery_rate"]["denominator"] == 1
    assert payload["metrics"]["verified_recovery_rate"]["value"] == 0.0


def test_benchmark_module_does_not_import_execution_or_network_authority() -> None:
    adapter_source = Path("app/services/microremed_result_adapter.py").read_text(encoding="utf-8")
    benchmark_source = Path("app/services/remediation_outcome_benchmark_p109.py").read_text(encoding="utf-8")
    forbidden = (
        "socket",
        "requests",
        "urllib",
        "boto3",
        "sqlalchemy",
        "psycopg",
        "ActionService",
    )

    for token in forbidden:
        assert token not in adapter_source
        assert token not in benchmark_source

    forbidden_imports = ("subprocess", "kubernetes", "ansible")
    for token in forbidden_imports:
        assert f"import {token}" not in adapter_source
        assert f"from {token}" not in adapter_source
        assert f"import {token}" not in benchmark_source
        assert f"from {token}" not in benchmark_source
