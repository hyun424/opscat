from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.hypothesis_reranker import HypothesisRerankerReport, build_hypothesis_reranker_report, render_hypothesis_reranker_markdown

CASES = Path("evals/investigator/p48_rerank_cases.json")


def test_hypothesis_reranker_updates_top_hypotheses_and_records_anti_anchoring() -> None:
    payload = build_hypothesis_reranker_report(CASES).to_dict()

    assert isinstance(build_hypothesis_reranker_report(CASES), HypothesisRerankerReport)
    assert payload["summary"]["case_count"] == 2
    assert payload["summary"]["expected_top_match_ratio"] == 1.0
    assert payload["summary"]["anti_anchoring_demotions"] >= 1
    assert payload["summary"]["unsafe_action_count"] == 0
    changed = [case for case in payload["cases"] if case["initial_top"] != case["final_top"]]
    assert changed and changed[0]["final_top"] == "database_saturation"
    assert all(case["action_boundary"]["auto_execute_allowed"] is False for case in payload["cases"])


def test_hypothesis_reranker_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p48.json"
    output_md = tmp_path / "p48.md"
    subprocess.run(
        ["python", "scripts/run_hypothesis_reranker.py", "--cases", str(CASES), "--output-json", str(output_json), "--output-md", str(output_md)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    markdown = output_md.read_text(encoding="utf-8")
    assert payload["summary"]["expected_top_match_ratio"] == 1.0
    assert "# OpsCat Hypothesis Re-ranker" in markdown
    assert "Anti-anchoring" in markdown
    assert render_hypothesis_reranker_markdown(payload).startswith("# OpsCat Hypothesis Re-ranker")
