from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.services.p176_release import build_readiness_artifact, load_json
from scripts import run_p176_qualification

ROOT = Path(__file__).resolve().parents[1]


def test_runner_no_results_writes_only_readiness_artifact(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_p176_qualification.py", "--output-dir", str(tmp_path)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "p176_not_executed_no_observed_outcomes"
    assert (tmp_path / "readiness-not-executed.json").is_file()
    assert not (tmp_path / "release-evidence.json").exists()
    readiness = load_json(tmp_path / "readiness-not-executed.json")
    assert readiness["qualified"] is False


def test_runner_partial_results_fail_without_fabricating_outputs(tmp_path: Path) -> None:
    outcomes = tmp_path / "outcomes.json"
    outcomes.write_text("[]\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "scripts/run_p176_qualification.py", "--outcomes", str(outcomes), "--output-dir", str(tmp_path)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "require --outcomes --healthy-results --safety-counters --agent-ledger --evaluator-ledger" in result.stderr
    assert not (tmp_path / "release-evidence.json").exists()


def test_runner_rejects_partial_live_release_args_without_fabricating_outputs(tmp_path: Path) -> None:
    outcomes = _write_json(tmp_path / "outcomes.json", [])
    healthy_results = _write_json(tmp_path / "healthy-results.json", [])
    safety_counters = _write_json(tmp_path / "safety-counters.json", {})
    agent_ledger = _write_json(tmp_path / "agent-ledger.json", [])
    evaluator_ledger = _write_json(tmp_path / "evaluator-ledger.json", [])
    release_inputs_manifest = _write_json(tmp_path / "release-inputs-manifest.json", {})

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_p176_qualification.py",
            "--outcomes",
            str(outcomes),
            "--healthy-results",
            str(healthy_results),
            "--safety-counters",
            str(safety_counters),
            "--agent-ledger",
            str(agent_ledger),
            "--evaluator-ledger",
            str(evaluator_ledger),
            "--release-inputs-manifest",
            str(release_inputs_manifest),
            "--output-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "live evidence args require all or none" in result.stderr
    assert not (tmp_path / "release-evidence.json").exists()


def test_runner_passes_live_release_args_to_release_builder(tmp_path: Path, monkeypatch: Any) -> None:
    inputs = {
        "outcomes": [{"episode_id": "episode-1"}],
        "healthy_results": [{"window_id": "window-1"}],
        "safety_counters": {"manual_override": 0},
        "agent_ledger": [{"record_hash": "sha256:" + "a" * 64}],
        "evaluator_ledger": [{"record_hash": "sha256:" + "b" * 64}],
        "release_inputs_manifest": {"manifest_hash": "sha256:" + "c" * 64},
        "live_artifact_manifest": {"manifest_hash": "sha256:" + "d" * 64},
        "billing_report": {"billing_report_hash": "sha256:" + "e" * 64},
        "teardown_proof": {"teardown_hash": "sha256:" + "f" * 64},
    }
    paths = {name: _write_json(tmp_path / f"{name}.json", value) for name, value in inputs.items()}
    captured: dict[str, Any] = {}

    def fake_build_release_artifacts(**kwargs: Any) -> dict[str, dict[str, Any]]:
        captured.update(kwargs)
        return {
            "report": {"report_hash": "sha256:" + "1" * 64},
            "denominator_report": {"denominator_report_hash": "sha256:" + "2" * 64},
            "representativeness_report": {"representativeness_report_hash": "sha256:" + "3" * 64},
            "freeze_manifest": {"manifest_hash": "sha256:" + "4" * 64},
        }

    monkeypatch.setattr(run_p176_qualification, "build_release_artifacts", fake_build_release_artifacts)

    result = run_p176_qualification.main(
        [
            "--outcomes",
            str(paths["outcomes"]),
            "--healthy-results",
            str(paths["healthy_results"]),
            "--safety-counters",
            str(paths["safety_counters"]),
            "--agent-ledger",
            str(paths["agent_ledger"]),
            "--evaluator-ledger",
            str(paths["evaluator_ledger"]),
            "--release-inputs-manifest",
            str(paths["release_inputs_manifest"]),
            "--live-artifact-manifest",
            str(paths["live_artifact_manifest"]),
            "--billing-report",
            str(paths["billing_report"]),
            "--teardown-proof",
            str(paths["teardown_proof"]),
            "--terminal-stop-at",
            "2026-07-18T00:00:00Z",
            "--output-dir",
            str(tmp_path / "output"),
        ]
    )

    assert result == 0
    assert captured["release_inputs_manifest"] == inputs["release_inputs_manifest"]
    assert captured["live_artifact_manifest"] == inputs["live_artifact_manifest"]
    assert captured["billing_report"] == inputs["billing_report"]
    assert captured["teardown_proof"] == inputs["teardown_proof"]
    assert captured["terminal_stop_at"] == "2026-07-18T00:00:00Z"
    assert (tmp_path / "output" / "freeze-manifest.json").is_file()


def test_stored_readiness_matches_current_predecessor_and_campaign() -> None:
    stored = load_json(ROOT / "evals/p176/output/readiness-not-executed.json")
    assert stored == build_readiness_artifact(project_root=ROOT)


def _write_json(path: Path, value: Any) -> Path:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    return path
