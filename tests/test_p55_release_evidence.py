from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p55_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p55-ticket-roadmap.md").read_text(encoding="utf-8")
    final_summary = Path("docs/operations/p55-final-summary.md").read_text(encoding="utf-8")
    for required in [
        "P55-001",
        "P55-002",
        "P55-003",
        "P55-004",
        "P55-005",
        "P55-006",
        "P55-007",
        "Candidate Benchmark Promotion Gate",
    ]:
        assert required in roadmap
    for required in [
        "P55 Candidate Benchmark Promotion Gate Evidence",
        "app/services/candidate_benchmark_promotion_gate.py",
        "scripts/run_candidate_benchmark_promotion_gate.py",
        "tests/test_candidate_benchmark_promotion_gate.py",
        "/tmp/opscat-candidate-benchmark-promotion-gate-latest.md",
    ]:
        assert required in release
    for required in [
        "P55-001",
        "P55-002",
        "P55-003",
        "P55-004",
        "P55-005",
        "P55-006",
        "P55-007",
        "app/services/candidate_benchmark_promotion_gate.py",
        "scripts/run_candidate_benchmark_promotion_gate.py",
    ]:
        assert required in final_summary
    assert "candidate_benchmark_promotion_gate_smoke" in verify
    assert all(marker not in release + roadmap + final_summary for marker in SECRET_MARKERS)
