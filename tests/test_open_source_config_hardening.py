from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.open_source_config_hardening import (
    OpenSourceConfigHardeningReport,
    render_open_source_config_hardening_markdown,
    run_open_source_config_hardening_fixture,
)

MANIFEST = Path("evals/config/p37_config_manifest.json")


def test_open_source_config_hardening_scores_safe_templates() -> None:
    report = run_open_source_config_hardening_fixture(MANIFEST)
    payload = report.to_dict()

    assert isinstance(report, OpenSourceConfigHardeningReport)
    assert payload["summary"]["checked_surface_count"] >= 4
    assert payload["score"]["template_pass_rate"] == 1.0
    assert payload["score"]["secret_safety_rate"] == 1.0
    assert payload["score"]["safe_default_rate"] == 1.0
    assert payload["score"]["real_secret_count"] == 0
    assert payload["score"]["unsafe_default_count"] == 0
    assert payload["boundary"]["reads_real_env_files"] is False
    assert payload["boundary"]["auth_session_work_enabled"] is False
    assert payload["boundary"]["remediation_execution_enabled"] is False


def test_open_source_config_hardening_preserves_placeholders_and_blocks_secret_markers() -> None:
    payload = run_open_source_config_hardening_fixture(MANIFEST).to_dict()
    serialized = json.dumps(payload)
    by_id = {surface["surface_id"]: surface for surface in payload["surfaces"]}

    assert by_id["local-example"]["missing_placeholder_count"] == 0
    assert by_id["local-example"]["unsafe_default_count"] == 0
    assert all(surface["real_secret_count"] == 0 for surface in payload["surfaces"])
    assert "${DATADOG_API_KEY}" in serialized
    assert "nvapi-" not in serialized
    assert "actual-secret-value" not in serialized


def test_open_source_config_hardening_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p37.json"
    output_md = tmp_path / "p37.md"

    subprocess.run(
        [
            "python",
            "scripts/run_open_source_config_hardening.py",
            "--manifest",
            str(MANIFEST),
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
    assert payload["score"]["real_secret_count"] == 0
    assert "# OpsCat Open-source Config Hardening Report" in markdown
    assert "Safe defaults" in markdown
    assert render_open_source_config_hardening_markdown(payload).startswith("# OpsCat Open-source Config Hardening Report")
