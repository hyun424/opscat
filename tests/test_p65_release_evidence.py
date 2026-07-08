from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = (
    "sk_live_",
    "xoxb-",
    "ghp_",
    "sntrys_",
    "BEGIN PRIVATE KEY",
    "prod-token",
    "nvapi-",
    "actual-secret-value",
    "mock-grafana-read-token",
    "provider://opscat/staging/read-only/grafana-token",
    "Authorization",
    "Bearer",
)


def test_p65_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p65-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p65-final-summary.md").read_text(encoding="utf-8")
    for required in ["P65-001", "P65-002", "P65-003", "P65-004", "P65-005", "P65-006", "P65-007", "P65-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P65 Real Staging Read-only Dry Attach Evidence",
        "evals/staging/p65_real_staging_dry_attach.json",
        "app/services/real_staging_dry_attach.py",
        "scripts/run_real_staging_dry_attach.py",
        "tests/test_real_staging_dry_attach.py",
        "/tmp/opscat-real-staging-dry-attach-latest.md",
    ]:
        assert required in release
    assert "real_staging_dry_attach_smoke" in verify
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
