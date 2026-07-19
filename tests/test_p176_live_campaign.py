from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.services.p147_p152_contracts import file_hash, stable_hash
from app.services.p176_campaign import generate_p176_campaign
from app.services.p176_live_bridge import load_json
from tests.test_p176_live_bridge import _write_reviewed_plan_artifacts, _write_valid_live_run

ROOT = Path(__file__).resolve().parents[1]


def test_cli_emits_deterministic_readiness_only_artifacts_when_observations_are_missing(tmp_path: Path) -> None:
    run_dir = tmp_path / "readiness-run"
    run_dir.mkdir()

    first = _run_cli(run_dir)
    second = _run_cli(run_dir)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    first_payload = json.loads(first.stdout)
    second_payload = json.loads(second.stdout)
    readiness = load_json(run_dir / "live-campaign-readiness.json")
    state = load_json(run_dir / "live-campaign-state.json")
    campaign = generate_p176_campaign()

    assert first_payload["status"] == "readiness_only"
    assert second_payload["readiness_hash"] == first_payload["readiness_hash"]
    assert readiness["status"] == "p176_live_campaign_readiness_only"
    assert readiness["qualification_artifacts_emitted"] is False
    assert readiness["cloud_apply_performed"] is False
    assert readiness["fault_mutation_performed"] is False
    assert readiness["fabricated_outcome_count"] == 0
    assert readiness["expected_episode_count"] == 480
    assert readiness["expected_healthy_window_count"] == 240
    assert readiness["campaign_hash"] == campaign["campaign_hash"]
    assert readiness["input_manifest_hash"] == file_hash(ROOT / "evals/p176/input/manifest.json")
    assert readiness["readiness_hash"] == stable_hash(
        {key: value for key, value in readiness.items() if key != "readiness_hash"}
    )
    assert state["status"] == "readiness_only"
    assert state["readiness_hash"] == readiness["readiness_hash"]
    assert not (run_dir / "live-outcomes.jsonl").exists()
    assert not (run_dir / "release-inputs-manifest.json").exists()


def test_cli_resumes_observed_run_and_delegates_exact_strata_materialization(tmp_path: Path) -> None:
    run_dir = _write_valid_live_run(tmp_path / "observed-run")
    plan_paths = _write_reviewed_plan_artifacts(run_dir)

    first = _run_cli(run_dir, plan_paths=plan_paths)
    second = _run_cli(run_dir)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    payload = json.loads(second.stdout)
    release_manifest = load_json(run_dir / "release-inputs-manifest.json")
    reconciliation = load_json(run_dir / "strata-reconciliation.json")
    state = load_json(run_dir / "live-campaign-state.json")

    assert payload["status"] == "p176_disposable_gcp_live_lab_evidence_ready"
    assert payload["manifest_hash"] == release_manifest["manifest_hash"]
    assert release_manifest["build_release_artifacts_target"] == "app.services.p176_release.build_release_artifacts"
    assert release_manifest["input_manifest_hash"] == file_hash(ROOT / "evals/p176/input/manifest.json")
    assert reconciliation["matches_campaign_denominators"] is True
    assert sum(reconciliation["family_counts"].values()) == 480
    assert set(reconciliation["family_counts"].values()) == {16}
    assert sum(reconciliation["telemetry_class_window_counts"].values()) == 240
    assert set(reconciliation["telemetry_class_window_counts"].values()) == {30}
    assert state["status"] == "p176_disposable_gcp_live_lab_evidence_ready"
    assert state["release_inputs_manifest_hash"] == release_manifest["manifest_hash"]
    assert state["reviewed_plan_artifacts"] == {
        "reviewed_apply_plan_artifact_path": "p176-live.tfplan.json",
        "reviewed_teardown_plan_artifact_path": "p176-live-destroy.tfplan",
        "reviewed_cost_cutoff_apply_plan_artifact_path": "p176-cost-cutoff.tfplan.json",
        "reviewed_cost_cutoff_destroy_plan_artifact_path": "p176-cost-cutoff-destroy.tfplan",
    }


def test_cli_observed_mode_requires_all_reviewed_plan_artifacts(tmp_path: Path) -> None:
    run_dir = _write_valid_live_run(tmp_path / "observed-missing-plans")

    result = _run_cli(run_dir)

    assert result.returncode == 1
    payload = json.loads(result.stderr)
    assert payload["status"] == "blocked"
    assert payload["error"] == "reviewed_plan_artifact_paths_required"


def test_cli_observed_mode_rejects_incomplete_reviewed_plan_artifacts(tmp_path: Path) -> None:
    run_dir = _write_valid_live_run(tmp_path / "observed-incomplete-plans")
    plan_paths = _write_reviewed_plan_artifacts(run_dir)

    result = _run_cli(run_dir, plan_paths={key: value for key, value in plan_paths.items() if key != "lab_destroy"})

    assert result.returncode == 1
    payload = json.loads(result.stderr)
    assert payload["status"] == "blocked"
    assert payload["error"] == "reviewed_plan_artifact_paths_incomplete"


def test_cli_observed_mode_rejects_outside_root_reviewed_plan_artifact(tmp_path: Path) -> None:
    run_dir = _write_valid_live_run(tmp_path / "observed-outside-plan")
    plan_paths = _write_reviewed_plan_artifacts(run_dir)
    outside = tmp_path / "outside.tfplan"
    outside.write_bytes(plan_paths["lab_apply"].read_bytes())

    result = _run_cli(run_dir, plan_paths={**plan_paths, "lab_apply": outside})

    assert result.returncode == 1
    payload = json.loads(result.stderr)
    assert payload["status"] == "blocked"
    assert payload["error"] == "reviewed_apply_plan_artifact_path_outside_run_evidence_root"


def test_cli_observed_mode_rejects_symlink_reviewed_plan_artifact(tmp_path: Path) -> None:
    run_dir = _write_valid_live_run(tmp_path / "observed-symlink-plan")
    plan_paths = _write_reviewed_plan_artifacts(run_dir)
    symlink = run_dir / "reviewed-apply-link.tfplan"
    symlink.symlink_to(plan_paths["lab_apply"].name)

    result = _run_cli(run_dir, plan_paths={**plan_paths, "lab_apply": symlink})

    assert result.returncode == 1
    payload = json.loads(result.stderr)
    assert payload["status"] == "blocked"
    assert payload["error"] == "reviewed_apply_plan_artifact_path_symlink"


def test_cli_fails_closed_on_frozen_campaign_or_input_hash_mismatch(tmp_path: Path) -> None:
    run_dir = tmp_path / "mismatch-run"
    run_dir.mkdir()
    state = {
        "schema_version": "p176.live_campaign_state.v1",
        "phase": "p176",
        "run_id": "p176-live-mismatch",
        "campaign_hash": "sha256:" + "0" * 64,
        "input_manifest_hash": file_hash(ROOT / "evals/p176/input/manifest.json"),
        "status": "readiness_only",
        "completed_steps": ["frozen_inputs_validated"],
        "state_hash": "",
    }
    state["state_hash"] = stable_hash({key: value for key, value in state.items() if key != "state_hash"})
    (run_dir / "live-campaign-state.json").write_text(json.dumps(state, sort_keys=True), encoding="utf-8")

    result = _run_cli(run_dir)

    assert result.returncode == 1
    payload = json.loads(result.stderr)
    assert payload["status"] == "blocked"
    assert payload["error"] == "state_campaign_hash_mismatch"


def test_cli_has_no_cloud_apply_or_fault_mutation_mode() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_p176_live_qualification.py", "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    help_text = result.stdout.lower()
    assert "mutate" not in help_text
    assert "fault" not in help_text


def _run_cli(run_dir: Path, *, plan_paths: dict[str, Path] | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "scripts/run_p176_live_qualification.py", "--run-dir", str(run_dir)]
    if plan_paths is not None:
        if "lab_apply" in plan_paths:
            command.extend(["--reviewed-apply-plan-artifact", str(plan_paths["lab_apply"])])
        if "lab_destroy" in plan_paths:
            command.extend(["--reviewed-teardown-plan-artifact", str(plan_paths["lab_destroy"])])
        if "cost_cutoff_apply" in plan_paths:
            command.extend(["--reviewed-cost-cutoff-apply-plan-artifact", str(plan_paths["cost_cutoff_apply"])])
        if "cost_cutoff_destroy" in plan_paths:
            command.extend(["--reviewed-cost-cutoff-destroy-plan-artifact", str(plan_paths["cost_cutoff_destroy"])])
    return subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
