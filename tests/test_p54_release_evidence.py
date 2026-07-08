from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p54_docs_and_verify_are_wired() -> None:
    summary = Path("docs/operations/p54-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p54-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "P54-001",
        "P54-002",
        "P54-003",
        "P54-004",
        "P54-005",
        "P54-006",
        "P54-007",
        "P54-008",
        "app/services/failure_driven_benchmark_improvement.py",
        "scripts/run_failure_driven_benchmark_improvement.py",
    ]:
        assert required in summary
    for required in [
        "P54 Failure-Driven Benchmark Improvement Evidence",
        "tests/test_failure_driven_benchmark_improvement.py",
        "/tmp/opscat-failure-driven-benchmark-improvement-latest.md",
    ]:
        assert required in release
    assert "failure_driven_benchmark_improvement_smoke" in verify
    assert "Failure-Driven Benchmark Improvement" in roadmap
    assert all(marker not in summary + release + roadmap for marker in SECRET_MARKERS)
