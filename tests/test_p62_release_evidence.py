from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p62_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p62-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p62-final-summary.md").read_text(encoding="utf-8")
    for required in ["P62-001", "P62-002", "P62-003", "P62-004", "P62-005", "P62-006", "P62-007", "P62-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P62 Staging Read-only Connector Contract Evidence",
        "evals/staging/p62_staging_connector_contract.json",
        "app/services/staging_read_only_connector_contract.py",
        "scripts/run_staging_read_only_connector_contract.py",
        "tests/test_staging_read_only_connector_contract.py",
        "/tmp/opscat-staging-read-only-connector-contract-latest.md",
    ]:
        assert required in release
    assert "staging_read_only_connector_contract_smoke" in verify
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
