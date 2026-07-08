from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p58_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p58-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p58-final-summary.md").read_text(encoding="utf-8")
    for required in ["P58-001", "P58-002", "P58-003", "P58-004", "P58-005", "P58-006", "P58-007"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P58 LLM Judgment Candidate Harness Evidence",
        "app/services/llm_judgment_candidate_harness.py",
        "scripts/run_llm_judgment_candidate_harness.py",
        "tests/test_llm_judgment_candidate_harness.py",
        "/tmp/opscat-llm-judgment-candidate-harness-latest.md",
    ]:
        assert required in release
    assert "llm_judgment_candidate_harness_smoke" in verify
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
