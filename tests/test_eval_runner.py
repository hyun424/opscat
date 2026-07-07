"""P4 eval runner contracts for operator-replacement trust evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.run_evals import run_evals


def test_eval_runner_executes_full_golden_corpus_and_writes_reports(tmp_path: Path) -> None:
    output_json = tmp_path / "opscat-evals.json"
    output_md = tmp_path / "opscat-evals.md"

    summary = run_evals(
        golden_dir=Path("evals/golden"),
        output_json=output_json,
        output_md=output_md,
    )

    assert summary["total"] >= 20
    assert summary["passed"] == summary["total"]
    assert summary["failed"] == 0
    assert output_json.exists()
    assert output_md.exists()

    payload = json.loads(output_json.read_text())
    assert payload["summary"]["passed"] == summary["passed"]
    assert {item["scenario"] for item in payload["results"]} >= {
        "payment_bad_deploy",
        "external_api_timeout",
        "worker_queue_backlog",
        "duplicate_alert_storm",
        "prompt_injection_log",
        "secret_bearing_alert",
        "protected_auth_incident",
    }
    markdown = output_md.read_text()
    assert "# OpsCat Eval Report" in markdown
    assert "operator replacement" in markdown.lower()
    assert "| Scenario |" in markdown


def test_eval_runner_reports_failed_expectation_without_side_effecting_success(tmp_path: Path) -> None:
    source = json.loads(Path("evals/golden/payment_bad_deploy.json").read_text())
    source["scenario"] = "impossible_expectation_probe"
    source["input_alert"]["scenario"] = "payment_bad_deploy"
    source["input_alert"]["idempotency_key"] = "impossible-expectation-probe"
    source["expected"]["top_cause_contains"] = "this cause cannot appear"
    bad_dir = tmp_path / "golden"
    bad_dir.mkdir()
    (bad_dir / "impossible_expectation_probe.json").write_text(json.dumps(source))

    summary = run_evals(golden_dir=bad_dir)

    assert summary["total"] == 1
    assert summary["passed"] == 0
    assert summary["failed"] == 1
    result: dict[str, Any] = summary["results"][0]
    assert result["scenario"] == "impossible_expectation_probe"
    assert result["passed"] is False
    assert result["checks"]["cause"]["ok"] is False
