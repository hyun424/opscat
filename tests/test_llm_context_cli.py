from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_context_builder_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    output_json = tmp_path / "context.json"
    output_md = tmp_path / "context.md"

    subprocess.run(
        [
            "python",
            "scripts/build_llm_context.py",
            "--cases",
            "evals/judgment/seed/cases.json",
            "--case-id",
            "seed-loghub-injection-block",
            "--max-evidence",
            "6",
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
    assert payload["local_mock_only"] is True
    assert payload["model_calls_enabled"] is False
    assert any(item["risk_flags"] for item in payload["evidence"])
    assert "# OpsCat LLM Context Packet" in markdown
    assert "no model calls" in markdown.lower()
    assert "local/mock" in markdown
