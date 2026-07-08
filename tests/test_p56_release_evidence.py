from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p56_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p56-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p56-final-summary.md").read_text(encoding="utf-8")
    for required in ["P56-001", "P56-002", "P56-003", "P56-004", "P56-005", "P56-006", "P56-007"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P56 Candidate Benchmark Regression Runner Evidence",
        "app/services/candidate_benchmark_regression_runner.py",
        "scripts/run_candidate_benchmark_regression_runner.py",
        "tests/test_candidate_benchmark_regression_runner.py",
        "/tmp/opscat-candidate-benchmark-regression-runner-latest.md",
    ]:
        assert required in release
    assert "candidate_benchmark_regression_runner_smoke" in verify
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
