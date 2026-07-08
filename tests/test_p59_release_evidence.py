from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p59_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p59-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p59-final-summary.md").read_text(encoding="utf-8")
    for required in ["P59-001", "P59-002", "P59-003", "P59-004", "P59-005", "P59-006", "P59-007"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P59 Hybrid Commander Comparator Evidence",
        "app/services/hybrid_commander_comparator.py",
        "scripts/run_hybrid_commander_comparator.py",
        "tests/test_hybrid_commander_comparator.py",
        "/tmp/opscat-hybrid-commander-comparator-latest.md",
    ]:
        assert required in release
    assert "hybrid_commander_comparator_smoke" in verify
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
