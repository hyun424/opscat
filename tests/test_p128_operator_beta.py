from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from app.services.p128_operator_beta import (
    P128_AUTHORITY_COUNTERS,
    build_operator_beta_html,
    build_p128_operator_beta_contract,
    load_p128_operator_scenarios,
    write_p128_outputs,
)

SCENARIOS = Path("evals/p128/input/operator-scenarios.json")


def test_p128_fixture_covers_required_evidence_surfaces_and_local_beta_boundary() -> None:
    scenarios = load_p128_operator_scenarios(SCENARIOS)
    contract = build_p128_operator_beta_contract(SCENARIOS)

    assert len(scenarios) >= 5
    assert contract["schema_version"] == "p128.ux_contract.v1"
    assert contract["summary"]["passed"] is True
    assert contract["summary"]["local_sandbox_beta_banner"] is True
    assert contract["summary"]["max_evidence_workflow_links"] <= 5
    assert contract["authority_counters"] == {counter: 0 for counter in P128_AUTHORITY_COUNTERS}
    assert set(contract["required_surfaces"]) <= set(contract["coverage"]["surfaces"])


def test_p128_html_is_server_rendered_read_only_escaped_and_secret_redacted() -> None:
    contract = build_p128_operator_beta_contract(SCENARIOS)
    html = build_operator_beta_html(contract)
    lowered = html.lower()

    assert "<main" in html
    assert "<nav" in html
    assert "<section" in html
    assert "Local/sandbox beta" in html
    assert "<script" not in lowered
    assert "<form" not in lowered
    assert "onclick=" not in lowered
    assert "mutation" not in lowered or "no mutation" in lowered
    assert "plain-secret" not in html
    assert "ops@example.com" not in html
    assert "[REDACTED]" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "operator replacement complete" not in lowered
    assert "credential_authority" in html
    assert 'data-testid="p128-beta-shell"' in html


def test_p128_runner_writes_contract_and_release_evidence(tmp_path: Path) -> None:
    contract_path = tmp_path / "ux-contract.json"
    evidence_path = tmp_path / "release-evidence.json"
    contract = build_p128_operator_beta_contract(SCENARIOS)
    evidence = write_p128_outputs(contract, output_json=contract_path, release_evidence_json=evidence_path)

    assert contract_path.is_file()
    assert evidence_path.is_file()
    assert evidence["schema_version"] == "p128.release_evidence.v1"
    assert evidence["gates"]["release_ready"] is True

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_p128_operator_beta.py",
            "--input",
            str(SCENARIOS),
            "--output-json",
            str(contract_path),
            "--release-evidence-json",
            str(evidence_path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    assert "OpsCat P128 operator beta" in completed.stdout
