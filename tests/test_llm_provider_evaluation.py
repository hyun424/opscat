from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.judgment_dataset import load_judgment_cases
from app.services.llm_judgment import MockLLMJudgmentProvider
from app.services.llm_provider_evaluation import (
    evaluate_llm_judgment_case,
    render_llm_provider_eval_markdown,
    run_llm_provider_evaluation,
)


def test_provider_eval_scores_mock_judgment_case_without_action_execution() -> None:
    case = next(case for case in load_judgment_cases("evals/judgment/seed/cases.json") if case.id == "seed-loghub-injection-block")

    result = evaluate_llm_judgment_case(case, provider=MockLLMJudgmentProvider())
    payload = result.to_dict()

    assert payload["case_id"] == "seed-loghub-injection-block"
    assert payload["provider"] == "mock"
    assert payload["schema_valid"] is True
    assert payload["citation_valid"] is True
    assert payload["action_execution_enabled"] is False
    assert payload["executed_actions"] == []
    assert payload["dimension_scores"]["safety"] == 1.0
    assert payload["dimension_scores"]["forbidden_action"] == 1.0
    assert payload["overall_score"] >= 0.75
    assert payload["passed"] is True


def test_provider_eval_runner_aggregates_scores_and_safety_regressions() -> None:
    cases = load_judgment_cases("evals/judgment/seed/cases.json")

    result = run_llm_provider_evaluation(cases, provider=MockLLMJudgmentProvider(), provider_name="mock")
    payload = result.to_dict()
    markdown = render_llm_provider_eval_markdown(result)

    assert payload["provider"] == "mock"
    assert payload["case_count"] == len(cases)
    assert payload["passed_count"] >= 1
    assert payload["overall_score"] > 0
    assert payload["local_mock_only"] is True
    assert payload["action_execution_enabled"] is False
    assert "# OpsCat LLM Provider Evaluation" in markdown
    assert "Safety regressions" in markdown
    assert "mock" in markdown


def test_provider_eval_cli_writes_json_and_markdown_mock(tmp_path: Path) -> None:
    output_json = tmp_path / "provider-eval.json"
    output_md = tmp_path / "provider-eval.md"

    subprocess.run(
        [
            "python",
            "scripts/run_llm_provider_eval.py",
            "--cases",
            "evals/judgment/seed/cases.json",
            "--provider",
            "mock",
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
    assert payload["provider"] == "mock"
    assert payload["case_count"] >= 4
    assert payload["action_execution_enabled"] is False
    assert "# OpsCat LLM Provider Evaluation" in markdown
    assert "no default external model/API calls" in markdown


def test_provider_eval_cli_loads_env_file_without_printing_key(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("NVIDIA_API_KEY=nvapi-test-secret\nOPSCAT_NVIDIA_MODEL=nvidia/nemotron-3-ultra-550b-a55b\n", encoding="utf-8")
    output_json = tmp_path / "provider-eval.json"

    completed = subprocess.run(
        [
            "python",
            "scripts/run_llm_provider_eval.py",
            "--cases",
            "evals/judgment/seed/cases.json",
            "--provider",
            "mock",
            "--env-file",
            str(env_file),
            "--max-cases",
            "1",
            "--output-json",
            str(output_json),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "nvapi-test-secret" not in completed.stdout
    assert "nvapi-test-secret" not in completed.stderr
    assert "nvapi-test-secret" not in output_json.read_text(encoding="utf-8")
