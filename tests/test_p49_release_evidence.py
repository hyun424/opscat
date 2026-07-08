from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p49_docs_and_verify_are_wired() -> None:
    summary = Path("docs/operations/p49-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    fixture = Path("evals/investigator/p49_remediation_verification_cases.json").read_text(encoding="utf-8")
    for required in [
        "P49-001",
        "P49-002",
        "P49-003",
        "P49-004",
        "P49-005",
        "P49-006",
        "P49-007",
        "P49-008",
        "app/services/remediation_verification_loop.py",
        "scripts/run_remediation_verification_loop.py",
    ]:
        assert required in summary
    for required in [
        "P49 Remediation Verification Loop Evidence",
        "tests/test_remediation_verification_loop.py",
        "/tmp/opscat-remediation-verification-loop-latest.md",
    ]:
        assert required in release
    assert "remediation_verification_loop_smoke" in verify
    assert "p49-db-pool-recovered" in fixture
    assert all(marker not in summary + release + fixture for marker in SECRET_MARKERS)
