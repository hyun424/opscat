from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p115_release_evidence import (
    P115_RELEASE_EVIDENCE_SCHEMA_VERSION,
    P115ReleaseEvidenceError,
    build_p115_release_evidence,
)
from app.services.p115_scenario_matrix import ROADMAP_FAMILIES
from scripts.build_p115_release_evidence import main as cli_main


def test_p115_release_bundle_is_contract_ready_without_p116_and_binds_frozen_artifacts() -> None:
    release = build_p115_release_evidence(
        safe_null_baseline=_baseline("safe_null"),
        deterministic_baseline=_baseline("deterministic_rule"),
        evaluator_report=_evaluator(outcome_qualified=False, include_all_families=True),
        reviewer_identity={"id": "reviewer-a"},
        builder_identity={"id": "builder-b"},
    )

    assert release["schema_version"] == P115_RELEASE_EVIDENCE_SCHEMA_VERSION
    assert release["release_status"] == "p115_contract_ready"
    assert release["contract_ready"] is True
    assert release["outcome_qualified"] is False
    assert release["denominators"]["case_count"] == 600
    assert release["denominators"]["matrix_denominators_complete"] is True
    assert release["gates"]["exact_zero_authority"] is True
    assert release["p116_import"]["present"] is False
    assert release["artifact_hashes"]["scenario_matrix"].startswith("sha256:")
    assert release["release_evidence_hash"] == stable_hash({key: value for key, value in release.items() if key != "release_evidence_hash"})


def test_p115_release_becomes_outcome_qualified_only_with_qualified_p116_and_thresholds() -> None:
    release = build_p115_release_evidence(
        safe_null_baseline=_baseline("safe_null"),
        deterministic_baseline=_baseline("deterministic_rule"),
        evaluator_report=_evaluator(outcome_qualified=True, include_all_families=True),
        p116_release_evidence=_p116(outcome_qualified=True),
        reviewer_identity={"id": "reviewer-a"},
        builder_identity={"id": "builder-b"},
    )

    assert release["release_status"] == "p115_outcome_qualified"
    assert release["outcome_qualified"] is True
    assert release["p116_import"]["record_hashes"] == ["sha256:" + "1" * 64, "sha256:" + "2" * 64]

    unqualified_p116 = build_p115_release_evidence(
        safe_null_baseline=_baseline("safe_null"),
        deterministic_baseline=_baseline("deterministic_rule"),
        evaluator_report=_evaluator(outcome_qualified=True, include_all_families=True),
        p116_release_evidence=_p116(outcome_qualified=False),
        reviewer_identity={"id": "reviewer-a"},
        builder_identity={"id": "builder-b"},
    )
    assert unqualified_p116["contract_ready"] is True
    assert unqualified_p116["outcome_qualified"] is False


def test_p115_release_fails_stale_hashes_self_review_missing_counters_and_aggregate_masking() -> None:
    stale = _baseline("safe_null")
    stale["counters"] = {**stale["counters"], "action_execution_count": 1}
    with pytest.raises(P115ReleaseEvidenceError, match="stale_hash:safe_null_baseline"):
        build_p115_release_evidence(
            safe_null_baseline=stale,
            deterministic_baseline=_baseline("deterministic_rule"),
            evaluator_report=_evaluator(outcome_qualified=False, include_all_families=True),
            reviewer_identity={"id": "reviewer-a"},
            builder_identity={"id": "builder-b"},
        )

    with pytest.raises(P115ReleaseEvidenceError, match="self_review"):
        build_p115_release_evidence(
            safe_null_baseline=_baseline("safe_null"),
            deterministic_baseline=_baseline("deterministic_rule"),
            evaluator_report=_evaluator(outcome_qualified=False, include_all_families=True),
            reviewer_identity={"id": "same"},
            builder_identity={"id": "same"},
        )

    missing_counters = _baseline("safe_null")
    missing_counters.pop("counters")
    missing_counters["report_hash"] = stable_hash({key: value for key, value in missing_counters.items() if key != "report_hash"})
    release_missing_counters = build_p115_release_evidence(
        safe_null_baseline=missing_counters,
        deterministic_baseline=_baseline("deterministic_rule"),
        evaluator_report=_evaluator(outcome_qualified=False, include_all_families=True),
        reviewer_identity={"id": "reviewer-a"},
        builder_identity={"id": "builder-b"},
    )
    assert release_missing_counters["contract_ready"] is False
    assert release_missing_counters["gates"]["authority_counters_present"] is False

    masked = build_p115_release_evidence(
        safe_null_baseline=_baseline("safe_null"),
        deterministic_baseline=_baseline("deterministic_rule"),
        evaluator_report=_evaluator(outcome_qualified=False, include_all_families=False),
        reviewer_identity={"id": "reviewer-a"},
        builder_identity={"id": "builder-b"},
    )
    assert masked["contract_ready"] is False
    assert masked["gates"]["no_aggregate_masking"] is False


def test_cli_writes_release_json_atomically(tmp_path: Path) -> None:
    safe_null = tmp_path / "safe-null.json"
    deterministic = tmp_path / "deterministic.json"
    evaluator = tmp_path / "evaluator.json"
    output = tmp_path / "nested" / "p115-release.json"
    markdown = tmp_path / "nested" / "p115-release.md"
    safe_null.write_text(json.dumps(_baseline("safe_null")), encoding="utf-8")
    deterministic.write_text(json.dumps(_baseline("deterministic_rule")), encoding="utf-8")
    evaluator.write_text(json.dumps(_evaluator(outcome_qualified=False, include_all_families=True)), encoding="utf-8")

    assert (
        cli_main(
            [
                "--safe-null-baseline",
                str(safe_null),
                "--deterministic-baseline",
                str(deterministic),
                "--evaluator-report",
                str(evaluator),
                "--reviewer-id",
                "reviewer-a",
                "--builder-id",
                "builder-b",
                "--output",
                str(output),
                "--markdown-output",
                str(markdown),
            ]
        )
        == 0
    )

    release = json.loads(output.read_text(encoding="utf-8"))
    assert release["schema_version"] == P115_RELEASE_EVIDENCE_SCHEMA_VERSION
    assert release["contract_ready"] is True
    assert markdown.read_text(encoding="utf-8").startswith("# P115 final release summary")
    assert not list(output.parent.glob("*.tmp"))


def _baseline(baseline_id: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "p115.baseline_report.v1",
        "baseline_id": baseline_id,
        "labels": [],
        "counters": {
            "action_execution_count": 0,
            "production_mutation_count": 0,
            "credential_access_count": 0,
            "subprocess_execution_count": 0,
            "external_network_count": 0,
            "auth_grant_count": 0,
            "llm_call_count": 0,
        },
    }
    payload["report_hash"] = stable_hash(payload)
    return payload


def _evaluator(*, outcome_qualified: bool, include_all_families: bool) -> dict[str, Any]:
    families = list(ROADMAP_FAMILIES if include_all_families else ROADMAP_FAMILIES[:-1])
    metrics = {
        "optimal_action_top1": _metric(90, 100),
        "optimal_action_top3": _metric(95, 100),
        "harmful_action_selection_rate": _metric(1, 100),
        "unnecessary_action_selection_rate": _metric(2, 100),
        "prerequisite_compliance": _metric(100, 100),
        "contraindication_avoidance": _metric(100, 100),
        "validation_completeness": _metric(100, 100),
        "rollback_completeness": _metric(100, 100),
        "evidence_citation_validity": _metric(99, 100),
        "correct_investigate_more_rate": _metric(95, 100),
    }
    payload: dict[str, Any] = {
        "schema_version": "p115.paired_score.v1",
        "release_status": "p115_outcome_qualified" if outcome_qualified else "p115_contract_ready",
        "outcome_qualified": outcome_qualified,
        "missing_p116_record_count": 0 if outcome_qualified else 10,
        "metrics": metrics,
        "partitions": [{"partition": "holdout", "family": family, "correct": 10, "denominator": 10, "value": 1.0} for family in families],
        "case_count": 100,
        "authority": {"action_execution_count": 0, "production_mutation_count": 0, "credential_access_count": 0},
        "counters": {
            "action_execution_count": 0,
            "production_mutation_count": 0,
            "credential_access_count": 0,
            "subprocess_execution_count": 0,
            "external_network_count": 0,
            "auth_grant_count": 0,
        },
    }
    payload["report_hash"] = stable_hash(payload)
    return payload


def _p116(*, outcome_qualified: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "p116.release_evidence.v1",
        "contract_ready": True,
        "outcome_qualified": outcome_qualified,
        "record_hashes": ["sha256:" + "1" * 64, "sha256:" + "2" * 64],
        "authority": {
            "production_authority_counters": {
                "external_network_enabled": 0,
                "filesystem_mutation_enabled": 0,
                "subprocess_execution_enabled": 0,
                "credentials_enabled": 0,
                "production_mutation_enabled": 0,
                "arbitrary_action_enabled": 0,
                "unattended_production_operation_claimed": 0,
            }
        },
    }
    payload["release_evidence_hash"] = stable_hash(payload)
    return payload


def _metric(numerator: int, denominator: int) -> dict[str, Any]:
    return {"numerator": numerator, "denominator": denominator, "value": round(numerator / denominator, 6)}
