from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.services.p109_release_evidence import (
    P109_RELEASE_PROFILE,
    REVIEW_HASH_KEYS,
    build_p109_authority_scan,
    produce_p109_release_evidence,
    stable_hash,
    validate_p109_independent_review,
)

ARTIFACT_HASHES = {
    "source_manifest": "sha256:" + "1" * 64,
    "raw_artifacts": "sha256:" + "2" * 64,
    "normalized_corpus": "sha256:" + "3" * 64,
    "diagnosis_report": "sha256:" + "4" * 64,
    "remediation_report": "sha256:" + "5" * 64,
    "contamination_report": "sha256:" + "6" * 64,
    "authority_scan": "sha256:" + "7" * 64,
    "release_profile": "sha256:" + "8" * 64,
    "implementation_revision": "sha256:" + "9" * 64,
}
HOLDOUT_HASH = "sha256:" + "a" * 64


def _metric(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": None if denominator == 0 else numerator / denominator,
        "status": "unevaluable" if denominator == 0 else "scored",
    }


def _release_metrics(*, harmful: int = 0, denominator: int = 4) -> dict[str, Any]:
    return {
        "verified_recovery_rate": _metric(2, denominator),
        "first_attempt_recovery_rate": _metric(1, denominator),
        "attempt_success_rate": _metric(2, denominator),
        "harmful_action_rate": _metric(harmful, denominator),
        "unnecessary_action_rate": _metric(0, denominator),
        "unsupported_record_rate": _metric(0, denominator),
        "truth_leak_rate": _metric(0, denominator),
    }


def _inputs(*, scored: bool = True, source_kind: str = "real_import") -> dict[str, Any]:
    return {
        "producer_id": "p109-producer",
        "benchmark_result": {
            "schema_version": "p109.remediation_outcome_benchmark.v1",
            "scored": scored,
            "release_evidence": False,
            "fixture_results_smoke_only": False,
            "external_execution": True,
            "release_trusted": True,
            "outcome_counts": {"verified_recovery": 2, "harmful": 0, "unnecessary": 0, "unsupported": 0, "leak": 0},
            "metrics": _release_metrics(denominator=4 if scored else 0),
            "by_dataset": {"rcaeval": _release_metrics(denominator=4 if scored else 0)},
            "by_system": {"checkout": _release_metrics(denominator=4 if scored else 0)},
            "by_fault_family": {"database": _release_metrics(denominator=4 if scored else 0)},
        },
        "holdout_report": {
            "schema_version": "p109.holdout_guard.v1",
            "accepted": True,
            "release_eligible": True,
            "authored_fixture_present": source_kind == "authored_fixture",
            "source_kind_counts": {source_kind: 4},
            "holdout_report_hash": HOLDOUT_HASH,
        },
        "authority_scan": {**build_p109_authority_scan(), "authority_scan_hash": ARTIFACT_HASHES["authority_scan"]},
        "verify_profile": {
            "profile": P109_RELEASE_PROFILE,
            "passed": True,
            "fresh": True,
            "release_profile_hash": ARTIFACT_HASHES["release_profile"],
        },
        "bound_artifact_hashes": ARTIFACT_HASHES,
        "dataset_mode": "real",
        "trusted_now": "2026-07-11T00:30:00Z",
    }


def _review(release_hash: str, artifact_hashes: dict[str, Any] | None = None) -> dict[str, Any]:
    hashes = artifact_hashes or ARTIFACT_HASHES
    return {
        "schema_version": "p109.independent_review.v1",
        "review_id": "p109-review-0001",
        "producer_id": "p109-producer",
        "reviewer": {"role": "verifier", "id": "p109-reviewer"},
        "verdict": "pass",
        "reviewed_at": "2026-07-11T00:20:00Z",
        "freshness": {"evidence_generated_at": "2026-07-11T00:10:00Z", "max_age_seconds": 3600, "fresh": True},
        "reviewed_artifact_hashes": {**hashes, "release_evidence": release_hash},
    }


def _produce(inputs: dict[str, Any] | None = None, review: dict[str, Any] | None = None) -> dict[str, Any]:
    base = inputs or _inputs()
    unsigned = produce_p109_release_evidence(**base, independent_review=None)
    final_review = review or _review(unsigned["release_evidence_hash"], unsigned["bound_artifact_hashes"])
    return produce_p109_release_evidence(**base, independent_review=final_review)


def test_p109_release_evidence_qualifies_only_real_scored_holdout_reviewed_data() -> None:
    evidence = _produce()

    assert evidence["schema_version"] == "p109.release_evidence.v1"
    assert evidence["release_qualified"] is True
    assert evidence["release_evidence_hash"].startswith("sha256:")
    assert evidence["six_release_gates"] == {
        "benchmark_scored": True,
        "holdout_clean": True,
        "authority_boundary_ready": True,
        "verify_profile_fresh": True,
        "real_data_not_authored_fixture": True,
        "independent_review_ready": True,
    }
    assert evidence["independent_review"]["accepted"] is True


def test_p109_authored_fixture_can_never_real_release_qualify() -> None:
    inputs = _inputs(source_kind="authored_fixture")

    evidence = _produce(inputs)

    assert evidence["release_qualified"] is False
    assert evidence["six_release_gates"]["real_data_not_authored_fixture"] is False
    assert any("authored fixture" in reason for reason in evidence["reasons"])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("external_execution", False),
        ("external_execution", None),
        ("release_trusted", False),
        ("release_trusted", None),
        ("fixture_results_smoke_only", True),
        ("fixture_results_smoke_only", None),
    ],
)
def test_p109_untrusted_or_non_external_remediation_never_release_qualifies(field: str, value: Any) -> None:
    inputs = _inputs()
    if value is None:
        inputs["benchmark_result"].pop(field)
    else:
        inputs["benchmark_result"][field] = value

    evidence = _produce(inputs)

    assert evidence["release_qualified"] is False
    assert evidence["six_release_gates"]["benchmark_scored"] is False
    assert any(field in reason or "fixture" in reason for reason in evidence["reasons"])


def test_p109_unevaluable_real_data_fails_release_and_cli_exits_nonzero(tmp_path: Path) -> None:
    inputs = _inputs(scored=False)
    unsigned = produce_p109_release_evidence(**inputs, independent_review=None)
    review = _review(unsigned["release_evidence_hash"], unsigned["bound_artifact_hashes"])
    benchmark_path = tmp_path / "benchmark.json"
    holdout_path = tmp_path / "holdout.json"
    review_path = tmp_path / "review.json"
    artifact_paths = _write_artifacts(tmp_path, inputs)
    benchmark_path.write_text(json.dumps(inputs["benchmark_result"], sort_keys=True), encoding="utf-8")
    holdout_path.write_text(json.dumps(inputs["holdout_report"], sort_keys=True), encoding="utf-8")
    review_path.write_text(json.dumps(review, sort_keys=True), encoding="utf-8")

    evidence = produce_p109_release_evidence(**inputs, independent_review=review)
    assert evidence["release_qualified"] is False
    assert evidence["six_release_gates"]["benchmark_scored"] is False

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_real_ops_benchmark.py",
            "--benchmark-result",
            str(benchmark_path),
            "--holdout-report",
            str(holdout_path),
            "--independent-review",
            str(review_path),
            "--source-manifest",
            str(artifact_paths["source_manifest"]),
            "--raw-artifacts",
            str(artifact_paths["raw_artifacts"]),
            "--normalized-corpus",
            str(artifact_paths["normalized_corpus"]),
            "--diagnosis-report",
            str(artifact_paths["diagnosis_report"]),
            "--remediation-report",
            str(artifact_paths["remediation_report"]),
            "--contamination-report",
            str(artifact_paths["contamination_report"]),
            "--authority-scan",
            str(artifact_paths["authority_scan"]),
            "--release-profile",
            str(artifact_paths["release_profile"]),
            "--implementation-revision",
            str(artifact_paths["implementation_revision"]),
            "--real-release",
            "--output-json",
            str(tmp_path / "release.json"),
            "--output-md",
            str(tmp_path / "release.md"),
        ],
        check=False,
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 1
    assert "benchmark_scored failed closed" in completed.stdout
    assert json.loads((tmp_path / "release.json").read_text(encoding="utf-8"))["release_qualified"] is False
    assert (tmp_path / "release.md").read_text(encoding="utf-8").startswith("# P109 Real Ops Benchmark Release Evidence")


def test_p109_independent_review_rejects_stale_hash_mismatch_and_self_review() -> None:
    inputs = _inputs()
    unsigned = produce_p109_release_evidence(**inputs, independent_review=None)
    review = _review(unsigned["release_evidence_hash"], unsigned["bound_artifact_hashes"])
    review["reviewer"]["id"] = "p109-producer"
    review["freshness"]["fresh"] = False
    review["reviewed_artifact_hashes"]["source_manifest"] = stable_hash({"stale": True})

    result = validate_p109_independent_review(
        review,
        expected_hashes={**unsigned["bound_artifact_hashes"], "release_evidence": unsigned["release_evidence_hash"]},
        producer_id="p109-producer",
        trusted_now="2026-07-11T00:30:00Z",
    )

    assert result["accepted"] is False
    assert result["fresh"] is False
    assert result["reviewed_artifact_hashes_match"] is False
    assert any("self-review" in reason or "stale" in reason for reason in result["reasons"])


def test_p109_release_metrics_fail_closed_on_missing_zero_or_safety_numerator() -> None:
    inputs = _inputs()
    inputs["benchmark_result"]["metrics"]["harmful_action_rate"]["numerator"] = 1
    inputs["benchmark_result"]["metrics"]["harmful_action_rate"]["value"] = 0.25
    evidence = _produce(inputs)

    assert evidence["release_qualified"] is False
    assert evidence["six_release_gates"]["benchmark_scored"] is False
    assert any("harmful_action_rate.numerator must be exact zero" in reason for reason in evidence["reasons"])

    missing = _inputs()
    del missing["benchmark_result"]["by_fault_family"]
    evidence = _produce(missing)
    assert evidence["release_qualified"] is False
    assert any("by_fault_family must be present" in reason for reason in evidence["reasons"])

    zero = _inputs(scored=False)
    evidence = _produce(zero)
    assert evidence["release_qualified"] is False
    assert any("denominator must be nonzero" in reason for reason in evidence["reasons"])


def test_p109_review_requires_expanded_hash_key_set() -> None:
    inputs = _inputs()
    unsigned = produce_p109_release_evidence(**inputs, independent_review=None)
    review = _review(unsigned["release_evidence_hash"], unsigned["bound_artifact_hashes"])
    review["reviewed_artifact_hashes"].pop("implementation_revision")

    result = validate_p109_independent_review(
        review,
        expected_hashes={**unsigned["bound_artifact_hashes"], "release_evidence": unsigned["release_evidence_hash"]},
        producer_id="p109-producer",
        trusted_now="2026-07-11T00:30:00Z",
    )

    assert tuple(review["reviewed_artifact_hashes"]) != REVIEW_HASH_KEYS
    assert result["accepted"] is False
    assert result["reviewed_artifact_hashes_match"] is False


def test_p109_real_release_cli_requires_artifact_inputs(tmp_path: Path) -> None:
    inputs = _inputs()
    benchmark_path = tmp_path / "benchmark.json"
    holdout_path = tmp_path / "holdout.json"
    benchmark_path.write_text(json.dumps(inputs["benchmark_result"], sort_keys=True), encoding="utf-8")
    holdout_path.write_text(json.dumps(inputs["holdout_report"], sort_keys=True), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_real_ops_benchmark.py",
            "--benchmark-result",
            str(benchmark_path),
            "--holdout-report",
            str(holdout_path),
            "--real-release",
        ],
        check=False,
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
    )

    assert completed.returncode != 0
    assert "requires explicit artifact inputs" in completed.stderr


def _write_artifacts(tmp_path: Path, inputs: dict[str, Any]) -> dict[str, Path]:
    payloads: dict[str, Any] = {
        "source_manifest": {"artifact": "source_manifest"},
        "raw_artifacts": {"artifact": "raw_artifacts"},
        "normalized_corpus": {"artifact": "normalized_corpus"},
        "diagnosis_report": {"artifact": "diagnosis_report"},
        "remediation_report": {"artifact": "remediation_report"},
        "contamination_report": {"artifact": "contamination_report"},
        "authority_scan": inputs["authority_scan"],
        "release_profile": inputs["verify_profile"],
        "implementation_revision": {"artifact": "implementation_revision"},
    }
    paths: dict[str, Path] = {}
    hashes: dict[str, str] = {}
    for key, payload in payloads.items():
        path = tmp_path / f"{key}.json"
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        paths[key] = path
        hashes[key] = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    inputs["bound_artifact_hashes"] = hashes
    inputs["authority_scan"] = {**inputs["authority_scan"], "authority_scan_hash": hashes["authority_scan"]}
    inputs["verify_profile"] = {**inputs["verify_profile"], "release_profile_hash": hashes["release_profile"]}
    return paths
