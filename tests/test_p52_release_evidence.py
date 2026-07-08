from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p52_docs_and_verify_are_wired() -> None:
    summary = Path("docs/operations/p52-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p52-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "P52-001",
        "P52-002",
        "P52-003",
        "P52-004",
        "P52-005",
        "P52-006",
        "P52-007",
        "P52-008",
        "app/services/failure_mining_loop.py",
        "scripts/run_failure_mining_loop.py",
    ]:
        assert required in summary
    for required in ["P52 Failure Mining Loop Evidence", "tests/test_failure_mining_loop.py", "/tmp/opscat-failure-mining-loop-latest.md"]:
        assert required in release
    assert "failure_mining_loop_smoke" in verify
    assert "Failure Mining Loop" in roadmap
    assert all(marker not in summary + release + roadmap for marker in SECRET_MARKERS)
