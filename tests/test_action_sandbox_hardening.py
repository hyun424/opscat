from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.action_sandbox_hardening import (
    SandboxDecision,
    SandboxReport,
    evaluate_action_sandbox_fixture,
    render_action_sandbox_markdown,
)

FIXTURE = Path("evals/actions/p79_action_sandbox_cases.json")


def test_action_sandbox_allows_only_local_read_only_without_approval() -> None:
    report = evaluate_action_sandbox_fixture(FIXTURE)
    payload = report.to_dict()
    decisions = {row["proposal_id"]: row for row in payload["decisions"]}

    assert isinstance(report, SandboxReport)
    safe_read = decisions["safe-read-only-context"]

    assert safe_read["decision"] == SandboxDecision.ALLOW.value
    assert safe_read["requires_approval"] is False
    assert safe_read["mock_only"] is True
    assert safe_read["checks"]["allowlisted"] is True
    assert safe_read["checks"]["dry_run_capable"] is True
    assert safe_read["checks"]["credential_boundary_clear"] is True
    assert safe_read["checks"]["network_boundary_clear"] is True
    assert safe_read["checks"]["production_mutation_boundary_clear"] is True
    assert safe_read["checks"]["shell_boundary_clear"] is True
    assert safe_read["blocked_reasons"] == []


def test_action_sandbox_routes_bounded_mutations_to_approval_or_mock_only() -> None:
    payload = evaluate_action_sandbox_fixture(FIXTURE).to_dict()
    decisions = {row["proposal_id"]: row for row in payload["decisions"]}

    approval = decisions["bounded-ticket-mutation"]
    dry_run_only = decisions["rollback-dry-run-only"]

    assert approval["decision"] == SandboxDecision.REQUIRE_APPROVAL.value
    assert approval["requires_approval"] is True
    assert approval["mock_only"] is True
    assert approval["checks"]["blast_radius_bounded"] is True
    assert approval["checks"]["reversible"] is True
    assert approval["approval_reasons"] == ["bounded_mutation_requires_human_approval"]

    assert dry_run_only["decision"] == SandboxDecision.MOCK_ONLY.value
    assert dry_run_only["mock_only"] is True
    assert dry_run_only["requires_approval"] is True
    assert "dry_run_only_without_approval" in dry_run_only["approval_reasons"]
    assert dry_run_only["checks"]["dry_run_capable"] is True


def test_action_sandbox_blocks_unbounded_or_external_boundaries() -> None:
    payload = evaluate_action_sandbox_fixture(FIXTURE).to_dict()
    decisions = {row["proposal_id"]: row for row in payload["decisions"]}

    production = decisions["prod-shell-restart"]
    credential = decisions["credential-network-read"]

    assert production["decision"] == SandboxDecision.BLOCK.value
    assert production["requires_approval"] is False
    assert production["mock_only"] is True
    assert "not_allowlisted" in production["blocked_reasons"]
    assert "production_mutation_boundary" in production["blocked_reasons"]
    assert "shell_execution_boundary" in production["blocked_reasons"]
    assert production["checks"]["production_mutation_boundary_clear"] is False
    assert production["checks"]["shell_boundary_clear"] is False

    assert credential["decision"] == SandboxDecision.BLOCK.value
    assert "credential_boundary" in credential["blocked_reasons"]
    assert "network_boundary" in credential["blocked_reasons"]
    assert credential["checks"]["credential_boundary_clear"] is False
    assert credential["checks"]["network_boundary_clear"] is False


def test_action_sandbox_report_summarizes_zero_execution_boundary() -> None:
    payload = evaluate_action_sandbox_fixture(FIXTURE).to_dict()

    assert payload["summary"]["proposal_count"] == 5
    assert payload["summary"]["allowed_count"] == 1
    assert payload["summary"]["approval_required_count"] == 1
    assert payload["summary"]["mock_only_count"] == 1
    assert payload["summary"]["blocked_count"] == 2
    assert payload["summary"]["action_execution_count"] == 0
    assert payload["summary"]["live_api_call_count"] == 0
    assert payload["summary"]["credential_read_count"] == 0
    assert payload["summary"]["network_call_count"] == 0
    assert payload["summary"]["production_mutation_count"] == 0
    assert payload["summary"]["shell_execution_count"] == 0
    assert payload["summary"]["passed"] is True
    assert payload["boundary"]["local_mock_only"] is True
    assert payload["boundary"]["action_execution_enabled"] is False
    assert payload["boundary"]["default_external_model_calls"] is False


def test_action_sandbox_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    output_json = tmp_path / "p79.json"
    output_md = tmp_path / "p79.md"

    subprocess.run(
        [
            "python",
            "scripts/run_action_sandbox_hardening.py",
            "--cases",
            str(FIXTURE),
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
    assert payload["summary"]["blocked_count"] == 2
    assert "# OpsCat Action Sandbox Hardening" in markdown
    assert "Zero-execution boundary" in markdown
    assert render_action_sandbox_markdown(payload).startswith("# OpsCat Action Sandbox Hardening")
