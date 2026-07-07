"""P4 release evidence index gates."""

from __future__ import annotations

from pathlib import Path


def test_release_evidence_index_lists_all_p4_gates_and_artifacts() -> None:
    path = Path("docs/release-evidence.md")

    assert path.exists()
    text = path.read_text()
    for required in [
        "# OpsCat P4 Release Evidence Index",
        "bash scripts/verify.sh",
        "scripts/run_evals.py",
        "scripts/run_connector_evals.py",
        "tests/test_operator_dashboard_e2e.py",
        "tests/test_eval_coverage_taxonomy.py",
        "docs/eval-report.md",
        "docs/eval-taxonomy.json",
        "/tmp/opscat-evals-latest.md",
        "/tmp/opscat-connector-evals-latest.md",
        "No real external side effects",
        "P5",
        "setup_permission",
        "setup_failure",
        "import_normalization",
    ]:
        assert required in text


def test_integration_verification_links_release_evidence_index() -> None:
    text = Path("docs/integration-verification.md").read_text()

    assert "docs/release-evidence.md" in text
    assert "Connector eval runner" in text
