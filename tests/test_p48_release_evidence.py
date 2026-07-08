from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p48_docs_and_verify_are_wired() -> None:
    summary = Path("docs/operations/p48-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    fixture = Path("evals/investigator/p48_rerank_cases.json").read_text(encoding="utf-8")
    for required in ["P48-001", "P48-002", "P48-003", "P48-004", "P48-005", "P48-006", "P48-007", "P48-008", "app/services/hypothesis_reranker.py", "scripts/run_hypothesis_reranker.py"]:
        assert required in summary
    for required in ["P48 Hypothesis Re-ranking Evidence", "tests/test_hypothesis_reranker.py", "/tmp/opscat-hypothesis-reranker-latest.md"]:
        assert required in release
    assert "hypothesis_reranker_smoke" in verify
    assert "p48-deploy-demoted-db-promoted" in fixture
    assert all(marker not in summary + release + fixture for marker in SECRET_MARKERS)
