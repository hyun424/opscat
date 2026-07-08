from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p53_docs_and_verify_are_wired() -> None:
    summary = Path("docs/operations/p53-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p53-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "P53-001",
        "P53-002",
        "P53-003",
        "P53-004",
        "P53-005",
        "P53-006",
        "P53-007",
        "P53-008",
        "app/services/failure_driven_improvement_pack.py",
        "scripts/run_failure_driven_improvement_pack.py",
    ]:
        assert required in summary
    for required in [
        "P53 Failure-Driven Improvement Pack Evidence",
        "tests/test_failure_driven_improvement_pack.py",
        "/tmp/opscat-failure-driven-improvement-pack-latest.md",
    ]:
        assert required in release
    assert "failure_driven_improvement_pack_smoke" in verify
    assert "Failure-Driven Improvement Pack" in roadmap
    assert all(marker not in summary + release + roadmap for marker in SECRET_MARKERS)
