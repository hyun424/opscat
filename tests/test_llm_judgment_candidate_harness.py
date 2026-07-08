from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.llm_judgment_candidate_harness import (
    LLMJudgmentCandidateHarnessReport,
    build_llm_judgment_candidate_harness_report,
    render_llm_judgment_candidate_harness_markdown,
)

CASES = Path("evals/investigator/p51_operator_judgment_benchmark_v2_cases.json")
MANIFEST = Path("evals/real_datasets/external/p44_benchmark_matrix_manifest.json")
JUDGMENT_CASES = Path("evals/judgment/seed/cases.json")


def test_llm_judgment_candidate_harness_gates_mock_llm_against_candidate_and_dataset_evidence() -> None:
    report = build_llm_judgment_candidate_harness_report(CASES, MANIFEST, JUDGMENT_CASES, provider_name="mock", max_cases=4)
    payload = report.to_dict()

    assert isinstance(report, LLMJudgmentCandidateHarnessReport)
    assert payload["summary"]["passed"] is True
    assert payload["summary"]["bridge_passed"] is True
    assert payload["summary"]["provider"] == "mock"
    assert payload["summary"]["llm_case_count"] == 4
    assert payload["summary"]["llm_pass_rate"] == 1.0
    assert payload["summary"]["llm_overall_score"] >= 0.9
    assert payload["summary"]["safety_regression_count"] == 0
    assert payload["summary"]["failed_case_count"] == 0
    assert payload["llm_evaluation"]["action_execution_enabled"] is False
    assert payload["llm_evaluation"]["local_mock_only"] is True
    assert payload["llm_evaluation"]["dimension_averages"]["citation"] == 1.0
    assert payload["llm_evaluation"]["dimension_averages"]["schema"] == 1.0
    assert all(gate["passed"] is True for gate in payload["harness_gates"])
    assert payload["boundary"]["default_external_model_calls"] is False
    assert payload["boundary"]["action_execution_enabled"] is False


def test_llm_judgment_candidate_harness_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p58.json"
    output_md = tmp_path / "p58.md"
    subprocess.run(
        [
            "python",
            "scripts/run_llm_judgment_candidate_harness.py",
            "--cases",
            str(CASES),
            "--manifest",
            str(MANIFEST),
            "--judgment-cases",
            str(JUDGMENT_CASES),
            "--provider",
            "mock",
            "--max-cases",
            "4",
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    markdown = output_md.read_text(encoding="utf-8")
    assert payload["summary"]["passed"] is True
    assert "# OpsCat LLM Judgment Candidate Harness" in markdown
    assert "Harness gates" in markdown
    assert "LLM evaluation" in markdown
    assert render_llm_judgment_candidate_harness_markdown(payload).startswith("# OpsCat LLM Judgment Candidate Harness")
