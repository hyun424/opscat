from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.services.p121_evaluator as p121_evaluator
from app.services.p121_evaluator import run_p121_frozen_evaluation
from app.services.p121_release_evidence import produce_p121_release_evidence, validate_p121_release_evidence


def test_frozen_unseen_evaluation_derives_outcomes_and_replays_recovery() -> None:
    report = run_p121_frozen_evaluation(seed=12101)
    assert report["case_count"] == 360
    assert report["aggregate"]["passed"] == 360
    assert len(report["crash_replay_points"]) >= 13
    assert report["manifest_contract"]["raw_inputs_only"] is True
    assert report["manifest_contract"]["hidden_truth_is_scorer_only"] is True
    assert report["restart_recovery"]["partial_l3_recovered"] is True
    assert report["restart_recovery"]["rollback_recovered"] is True
    assert report["restart_recovery"]["pending_rollback_replayed"] is True
    assert report["restart_recovery"]["pending_rollback_count_after_replay"] == 0
    assert report["authority"]["exact_nonlocal_authority_zero"] is True


def test_release_evidence_is_fresh_distinct_and_bounded() -> None:
    report = run_p121_frozen_evaluation(seed=12101)
    evidence = produce_p121_release_evidence(report=report, reviewer_id="reviewer", builder_id="builder")
    assert evidence["release_status"] == "p121_local_proactive_prevention_ready"
    assert "No production" in evidence["scope_limit"]
    assert validate_p121_release_evidence(evidence)["valid"] is True
    assert evidence["gates"]["raw_manifest_contract"] is True
    assert evidence["gates"]["durable_restart_recovery"] is True


def test_self_review_fails_closed() -> None:
    report = run_p121_frozen_evaluation(seed=12101)
    assert produce_p121_release_evidence(report=report, reviewer_id="same", builder_id="same")["release_status"] == "p121_blocked"


def test_pre_scored_manifest_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = json.loads(p121_evaluator._MANIFEST.read_text(encoding="utf-8"))
    manifest["cases"][0]["passed"] = True
    manifest["manifest_hash"] = p121_evaluator.stable_hash({key: value for key, value in manifest.items() if key != "manifest_hash"})
    bad_manifest = tmp_path / "manifest.json"
    bad_manifest.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    monkeypatch.setattr(p121_evaluator, "_MANIFEST", bad_manifest)
    with pytest.raises(ValueError, match="pre_scored_manifest_forbidden"):
        run_p121_frozen_evaluation(seed=12101)
