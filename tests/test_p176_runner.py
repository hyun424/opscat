from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.services.p176_release import build_readiness_artifact, load_json

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


def test_stored_readiness_matches_current_predecessor_and_campaign() -> None:
    stored = load_json(ROOT / "evals/p176/output/readiness-not-executed.json")
    assert stored == build_readiness_artifact(project_root=ROOT)
