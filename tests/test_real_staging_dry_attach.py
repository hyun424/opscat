from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.real_staging_dry_attach import (
    RealStagingDryAttachReport,
    render_real_staging_dry_attach_markdown,
    run_real_staging_dry_attach_fixture,
)

FIXTURE = Path("evals/staging/p65_real_staging_dry_attach.json")


def test_real_staging_dry_attach_builds_attach_ready_plan_without_network_or_env_reads() -> None:
    report = run_real_staging_dry_attach_fixture(FIXTURE)
    payload = report.to_dict()

    assert isinstance(report, RealStagingDryAttachReport)
    assert payload["summary"]["attachment_count"] == 4
    assert payload["summary"]["attach_ready_count"] == 3
    assert payload["summary"]["blocked_count"] == 1
    assert payload["summary"]["detach_plan_count"] == 3
    assert payload["summary"]["audit_handoff_count"] == 3
    assert payload["summary"]["passed"] is True
    assert payload["score"]["env_read_count"] == 0
    assert payload["score"]["real_credential_read_count"] == 0
    assert payload["score"]["network_call_count"] == 0
    assert payload["score"]["production_mutation_count"] == 0
    assert payload["score"]["action_execution_count"] == 0
    assert payload["boundary"]["dry_attach_only"] is True
    assert payload["boundary"]["reads_dotenv"] is False
    assert payload["boundary"]["real_network_enabled"] is False


def test_real_staging_dry_attach_requires_secret_provider_refs_and_audit_handoff() -> None:
    payload = run_real_staging_dry_attach_fixture(FIXTURE).to_dict()
    by_id = {item["attachment_id"]: item for item in payload["attachments"]}

    for attachment_id in (
        "p65-grafana-real-staging-dry-attach",
        "p65-sentry-real-staging-dry-attach",
        "p65-datadog-real-staging-dry-attach",
    ):
        attachment = by_id[attachment_id]
        assert attachment["status"] == "attach_ready_dry_run"
        assert attachment["audit_handoff"]["p64_decision"] == "approved_dry_run"
        assert attachment["credential_ref_fingerprint"]
        assert attachment["detach_plan"]["safe_to_disable_polling"] is True
        assert attachment["detach_plan"]["provider_mutation_required"] is False

    blocked = by_id["p65-prod-raw-token-blocked"]
    assert blocked["status"] == "blocked"
    assert "non_staging_environment" in blocked["reasons"]
    assert "raw_credential_value" in blocked["reasons"]
    assert "audit_handoff_not_approved" in blocked["reasons"]
    assert "non_get_method" in blocked["reasons"]
    assert "host_not_allowlisted" in blocked["reasons"]
    assert "polling_enabled_before_attach" in blocked["reasons"]


def test_real_staging_dry_attach_redacts_secret_values_and_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p65.json"
    output_md = tmp_path / "p65.md"

    subprocess.run(
        [
            "python",
            "scripts/run_real_staging_dry_attach.py",
            "--manifest",
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
    serialized = json.dumps(payload)
    markdown = output_md.read_text(encoding="utf-8")
    assert payload["summary"]["passed"] is True
    for forbidden in ["actual-secret-value", "mock-grafana-read-token", "Authorization", "Bearer", "provider://opscat/staging/read-only/grafana-token"]:
        assert forbidden not in serialized
        assert forbidden not in markdown
    assert "credential_ref_fingerprint" in serialized
    assert "# OpsCat Real Staging Read-only Dry Attach" in markdown
    assert "Detach plan" in markdown
    assert render_real_staging_dry_attach_markdown(payload).startswith("# OpsCat Real Staging Read-only Dry Attach")
