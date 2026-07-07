from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_llm_judgment_cli_writes_json_and_markdown_from_case(tmp_path: Path) -> None:
    output_json = tmp_path / "judgment.json"
    output_md = tmp_path / "judgment.md"

    subprocess.run(
        [
            "python",
            "scripts/run_llm_judgment.py",
            "--cases",
            "evals/judgment/seed/cases.json",
            "--case-id",
            "seed-loghub-injection-block",
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
    assert payload["local_mock_only"] is True
    assert payload["model_calls_enabled"] is False
    assert payload["action_execution_enabled"] is False
    assert payload["validation"]["valid"] is True
    assert payload["citation_check"]["valid"] is True
    assert payload["safety_gate"]["final_route"] in {"blocked", "human_required"}
    assert "# OpsCat LLM Judgment Report" in markdown
    assert "mock provider" in markdown.lower()
    assert "no action execution" in markdown.lower()


def test_llm_judgment_cli_accepts_prebuilt_context_packet(tmp_path: Path) -> None:
    context_json = tmp_path / "context.json"
    judgment_json = tmp_path / "judgment.json"
    subprocess.run(
        [
            "python",
            "scripts/build_llm_context.py",
            "--cases",
            "evals/judgment/seed/cases.json",
            "--case-id",
            "seed-loghub-injection-block",
            "--output-json",
            str(context_json),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            "python",
            "scripts/run_llm_judgment.py",
            "--context-json",
            str(context_json),
            "--provider",
            "mock",
            "--output-json",
            str(judgment_json),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(judgment_json.read_text(encoding="utf-8"))
    assert payload["context"]["boundary"]
    assert payload["provider"] == "mock"
    assert payload["safety_gate"]["executed_actions"] == []
