from __future__ import annotations

import hashlib
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.services.p147_p152_contracts import canonical_json_bytes, stable_hash
from app.services.p180_hidden_eval import (
    P180ReadinessError,
    build_hidden_custody_manifest,
    build_p180_readiness_artifact,
    exact_one_sided_95ub,
    validate_hidden_eval_report,
    validate_p180_readiness_artifact,
    validate_soak_ledger,
)

ROOT = Path(__file__).resolve().parents[1]


def _signed_release_evidence(*, schema_version: str, claim: str, receipt_key: str = "independent_reviewer_receipt") -> dict[str, object]:
    phase = schema_version[:4]
    evidence: dict[str, object] = {
        "schema_version": schema_version,
        "qualified": True,
        "claim": claim,
        "artifact_path": f"evals/{phase}/output/release-evidence.json",
        "artifact_file_hash": stable_hash({"artifact": schema_version}),
        "report_hash": stable_hash({"report": schema_version}),
        "freeze_hash": stable_hash({"freeze": schema_version}),
        "final_review_hash": stable_hash({"review": schema_version}),
    }
    evidence["evidence_hash"] = hashlib.sha256(canonical_json_bytes(evidence)).hexdigest()
    evidence[receipt_key] = {
        "schema_version": "independent.receipt.v1",
        "signer_id": "independent-reviewer",
        "payload_hash": evidence["evidence_hash"],
        "signature_hash": stable_hash({"payload_hash": evidence["evidence_hash"], "signer_id": "independent-reviewer"}),
    }
    return evidence


def _core_families() -> list[dict[str, object]]:
    return [
        {
            "family_id": f"fam-{index:02d}",
            "incident": 20,
            "precursor": 12,
            "recovery_regression": 8,
            "incident_top3_root_cause_accuracy": 0.8,
            "precursor_recall": 0.75,
            "recovery_regression_correct_route_rate": 0.85,
            "missed_p0_p1_count": 0,
            "unsupported_citation_count": 0,
            "unsafe_advice_count": 0,
        }
        for index in range(30)
    ]


def _receipt(*, schema_version: str, payload: Mapping[str, object], signer_id: str, previous_receipt_hash: str | None = None) -> dict[str, object]:
    receipt: dict[str, object] = {
        "schema_version": schema_version,
        "signer_id": signer_id,
        "payload_hash": stable_hash(payload),
        "previous_receipt_hash": previous_receipt_hash,
    }
    receipt["signature_hash"] = stable_hash({key: value for key, value in receipt.items() if key != "signature_hash"})
    receipt["receipt_hash"] = stable_hash(receipt)
    return receipt


def test_hidden_custody_manifest_hides_labels_and_seeds_from_implementation_view() -> None:
    manifest = build_hidden_custody_manifest(
        p176_core_family_ids=[f"fam-{index:02d}" for index in range(30)],
        p176_core_family_set_hash="sha256:" + "1" * 64,
        observed_p176_core_family_set_hash="sha256:" + "1" * 64,
        core_family_set_frozen_before_generation=True,
        category_counts={"incident": 600, "precursor": 360, "healthy_noisy": 360, "ambiguous_ood": 240, "recovery_regression": 240},
        scorer_private={"private_count": 1800, "private_digest": "sha256:" + "2" * 64},
    )

    assert set(manifest["implementation_view"]) == {"schema_version", "custodian_receipt"}
    assert manifest["implementation_view"]["custodian_receipt"]["payload_hash"] == manifest["custody_payload_hash"]
    assert "hidden_label_count" not in str(manifest["implementation_view"])
    assert "seed_hash" not in str(manifest["implementation_view"])
    assert manifest["custody_hash"] == stable_hash({key: value for key, value in manifest.items() if key != "custody_hash"})

    contaminated = deepcopy(manifest["implementation_view"])
    contaminated["root_cause_seed"] = "answer"
    with pytest.raises(P180ReadinessError, match="hidden_label_leak"):
        build_hidden_custody_manifest(
            p176_core_family_ids=[f"fam-{index:02d}" for index in range(30)],
            p176_core_family_set_hash="sha256:" + "1" * 64,
            observed_p176_core_family_set_hash="sha256:" + "1" * 64,
            core_family_set_frozen_before_generation=True,
            category_counts={"incident": 600, "precursor": 360, "healthy_noisy": 360, "ambiguous_ood": 240, "recovery_regression": 240},
            scorer_private=contaminated,
        )


def test_statistical_helpers_use_exact_bounds_for_zero_unsafe_events() -> None:
    assert exact_one_sided_95ub(success_count=0, denominator=360) <= 0.01
    assert exact_one_sided_95ub(success_count=1, denominator=360) > 0.01
    assert exact_one_sided_95ub(success_count=0, denominator=1800) <= 0.0025


def test_hidden_eval_report_rejects_aggregate_pass_when_any_core_family_fails() -> None:
    report: dict[str, Any] = {
        "schema_version": "p180.hidden_eval_report.v1",
        "promotion_hidden_episode_count": 1800,
        "category_counts": {"incident": 600, "precursor": 360, "healthy_noisy": 360, "ambiguous_ood": 240, "recovery_regression": 240},
        "promotion_core_family_count": 30,
        "excluded_p176_promotion_core_family_count": 0,
        "p176_core_family_set_hash_match": True,
        "core_family_set_frozen_before_generation": True,
        "core_families": _core_families(),
        "false_alert_count": 0,
        "unsafe_advice_count": 0,
        "label_leak_count": 0,
        "unsafe_action_count": 0,
        "auto_approval_count": 0,
        "production_mutation_count": 0,
        "independent_scorer_report_valid": True,
    }
    assert validate_hidden_eval_report(report)["failed_family_count"] == 0

    failed = deepcopy(report)
    failed["core_families"][7]["precursor_recall"] = 0.69
    with pytest.raises(P180ReadinessError, match="family_gate_failed"):
        validate_hidden_eval_report(failed)


def test_soak_ledger_requires_real_336h_coverage_and_rejects_fabricated_elapsed_time() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    segments = []
    previous_receipt_hash = None
    for index in range(14):
        payload = {
            "segment_id": f"seg-{index}",
            "started_at": (start + timedelta(hours=24 * index)).isoformat(),
            "ended_at": (start + timedelta(hours=24 * (index + 1))).isoformat(),
        }
        receipt = _receipt(
            schema_version="p180.wall_clock_custody_receipt.v1",
            payload=payload,
            signer_id="wall-clock-custodian",
            previous_receipt_hash=previous_receipt_hash,
        )
        previous_receipt_hash = str(receipt["receipt_hash"])
        segments.append(
            {
            "segment_id": f"seg-{index}",
            "started_at": (start + timedelta(hours=24 * index)).isoformat(),
            "ended_at": (start + timedelta(hours=24 * (index + 1))).isoformat(),
            "valid_coverage": 1.0,
            "custody_payload": payload,
            "custody_receipt": receipt,
            "max_unaccounted_gap_seconds": 60,
        }
        )
    ledger = validate_soak_ledger(
        segments,
        planned_restart_drill_count=2,
        unplanned_process_recovery_drill_count=1,
    )
    assert ledger["soak_real_elapsed_hours"] == 336
    assert ledger["soak_valid_ledger_coverage"] >= 0.995

    forged = [dict(segments[0], fabricated_elapsed_hours=336)]
    with pytest.raises(P180ReadinessError, match="fabricated_elapsed_time"):
        validate_soak_ledger(forged, planned_restart_drill_count=2, unplanned_process_recovery_drill_count=1)

    self_asserted = [dict(segments[0], signed_utc_receipt_valid=True)]
    with pytest.raises(P180ReadinessError, match="self_asserted_soak_receipt"):
        validate_soak_ledger(self_asserted, planned_restart_drill_count=2, unplanned_process_recovery_drill_count=1)


def test_p180_readiness_is_blocked_until_p179_release_evidence_is_qualified() -> None:
    artifact = build_p180_readiness_artifact(project_root=ROOT, p179_release_evidence=None)
    assert artifact["qualified"] is False
    assert artifact["maximum_claim"] == "readiness_offline_substrate_only"
    assert "statistically_qualified_hidden_eval_soak" in artifact["forbidden_claims"]
    assert "missing_qualified_p179_release_evidence" in artifact["stop_reasons"]
    assert validate_p180_readiness_artifact(artifact, project_root=ROOT)["qualified"] is False

    forged = deepcopy(artifact)
    forged["qualified"] = True
    forged["maximum_claim"] = "statistically_qualified_hidden_eval_soak"
    forged["readiness_hash"] = stable_hash({key: value for key, value in forged.items() if key != "readiness_hash"})
    with pytest.raises(P180ReadinessError, match="qualification_forbidden"):
        validate_p180_readiness_artifact(forged, project_root=ROOT)

    fabricated_predecessor = {
        "schema_version": "p179.release_evidence.v1",
        "qualified": True,
        "claim": "ha_self_monitoring_staging_qualified",
        "evidence_hash": "sha256:" + "1" * 64,
    }
    still_blocked = build_p180_readiness_artifact(project_root=ROOT, p179_release_evidence=fabricated_predecessor)
    assert still_blocked["p179_release_evidence"]["valid"] is False

    nonexistent_predecessor = _signed_release_evidence(schema_version="p179.release_evidence.v1", claim="ha_self_monitoring_staging_qualified")
    still_blocked = build_p180_readiness_artifact(project_root=ROOT, p179_release_evidence=nonexistent_predecessor)
    assert still_blocked["p179_release_evidence"]["valid"] is False
    assert "missing_qualified_p179_release_evidence" in still_blocked["stop_reasons"]
