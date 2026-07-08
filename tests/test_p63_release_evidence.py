from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value", "Authorization")


def test_p63_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p63-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p63-final-summary.md").read_text(encoding="utf-8")
    for required in ["P63-001", "P63-002", "P63-003", "P63-004", "P63-005", "P63-006", "P63-007", "P63-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P63 Staging Live Read-only Preflight Evidence",
        "evals/staging/p63_staging_live_preflight.json",
        "app/services/staging_live_read_only_preflight.py",
        "scripts/run_staging_live_read_only_preflight.py",
        "tests/test_staging_live_read_only_preflight.py",
        "/tmp/opscat-staging-live-read-only-preflight-latest.md",
    ]:
        assert required in release
    assert "staging_live_read_only_preflight_smoke" in verify
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
