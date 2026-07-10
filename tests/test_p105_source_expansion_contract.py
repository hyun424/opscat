from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

RELEASE_FAMILIES = {"database", "deploy", "queue"}
EXACT_FLOORS = {
    "held_out": {"evaluated_count": 30, "non_abstained_count": 24, "positive_count": 6, "incident_group_count": 4, "service_day_count": 2.0},
    "real_derived_shadow": {"evaluated_count": 20, "non_abstained_count": 16, "positive_count": 4, "incident_group_count": 3, "service_day_count": 1.0},
}


def _api() -> Any:
    return importlib.import_module("app.services.failure_forecast_engine")


def _write_json(path: Path, payload: Any) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _validator() -> Any:
    validator = getattr(_api(), "validate_p105_source_expansion_release_inputs", None)
    if validator is None:
        pytest.fail("P105-024 RED: expose validate_p105_source_expansion_release_inputs before source-expanded scoring.", pytrace=False)
    return validator


def test_downstream_materializer_rejects_missing_registry_and_eligibility_authority(tmp_path: Path) -> None:
    rows = _write_json(
        tmp_path / "rows.json",
        {
            "schema_version": "p105.release-qualified.rows.v1",
            "mode": "release_qualified",
            "rows": [{"row_id": "r1", "family": "queue", "source_window_id": "w1", "partition": "held_out"}],
        },
    )

    result = _validator()(rows_path=rows, source_registry=None, source_eligibility=None)

    assert "source_registry_missing" in result["validation_error_codes"]
    assert "source_eligibility_missing" in result["validation_error_codes"]
    assert result["failure_stage"] == "pre_scoring"
    assert result["release_gate"] == {"release_qualified": False, "p106_unlocked": False}


@pytest.mark.parametrize(
    "forbidden_authority",
    ["filename", "ordinal", "partition", "private_label", "p105_score", "p24_score", "floor_deficit", "post_incident_value"],
)
def test_family_authority_cannot_come_from_heuristics_or_labels(tmp_path: Path, forbidden_authority: str) -> None:
    registry = _write_json(tmp_path / "registry.json", {"schema_version": "p105.source-registry.v1", "sources": []})
    eligibility = _write_json(
        tmp_path / "eligibility.json",
        {
            "schema_version": "p105.source-eligibility.v1",
            "entries": [
                {
                    "source_key": "heuristic-source",
                    "source_window_id": "w1",
                    "family_candidate": "database",
                    "family_authority_source": forbidden_authority,
                    "eligible_for_release_floor": True,
                }
            ],
        },
    )

    result = _validator()(rows_path=None, source_registry=registry, source_eligibility=eligibility)

    assert "family_authority_not_reviewed_registry" in result["validation_error_codes"]
    assert result["release_gate"]["release_qualified"] is False
    assert result["release_gate"]["p106_unlocked"] is False


def test_actual_coverage_only_rejects_four_day_or_floor_sized_fabrication(tmp_path: Path) -> None:
    eligibility = _write_json(
        tmp_path / "eligibility.json",
        {
            "schema_version": "p105.source-eligibility.v1",
            "entries": [
                {
                    "source_key": "queue-harness",
                    "source_window_id": "queue-001",
                    "family_candidate": "queue",
                    "eligible_for_release_floor": True,
                    "coverage_interval_ids": ["fabricated-four-day"],
                    "coverage_seconds": 345600,
                    "coverage_source": "fixed_four_day_constant",
                }
            ],
        },
    )

    result = _validator()(source_registry=tmp_path / "registry.json", source_eligibility=eligibility)

    assert "actual_coverage_missing" in result["validation_error_codes"]
    assert "synthetic_four_day_coverage" in result["validation_error_codes"]
    assert result["counting_coverage_seconds"] == 0


def test_release_inputs_preserve_exact_floors_and_block_p106_until_macro_sequence_complete(tmp_path: Path) -> None:
    macro_sequence = _write_json(
        tmp_path / "macro-sequence.json",
        {
            "plan_review": {"approved": True},
            "red_contract_failures": {"recorded": True},
            "actual_source_runs": {"completed": True},
            "independent_code_review": {"approved": False},
            "independent_architecture_review": {"approved": False},
            "full_verification": {"passed": False},
        },
    )

    result = _validator()(macro_sequence=macro_sequence, expected_floors=EXACT_FLOORS, release_families=RELEASE_FAMILIES)

    assert result["qualification_floors"]["minimums"] == EXACT_FLOORS
    assert "independent_review_missing" in result["validation_error_codes"]
    assert "full_verification_missing" in result["validation_error_codes"]
    assert result["release_gate"]["release_qualified"] is False
    assert result["release_gate"]["p106_unlocked"] is False
