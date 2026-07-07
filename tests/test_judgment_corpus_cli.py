from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_p11_corpus_audit_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    output_json = tmp_path / "corpus-audit.json"
    output_md = tmp_path / "corpus-audit.md"
    corpus_out = tmp_path / "p11-corpus.json"

    completed = subprocess.run(
        [
            "python",
            "scripts/run_corpus_audit.py",
            "--write-corpus",
            str(corpus_out),
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
    corpus_payload = json.loads(corpus_out.read_text(encoding="utf-8"))

    assert completed.returncode == 0
    assert payload["passed"] is True
    assert payload["total_cases"] >= 50
    assert "# OpsCat Incident Corpus Audit" in markdown
    assert len(corpus_payload) == payload["total_cases"]
