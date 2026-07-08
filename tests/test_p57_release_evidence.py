from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p57_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p57-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p57-final-summary.md").read_text(encoding="utf-8")
    for required in ["P57-001", "P57-002", "P57-003", "P57-004", "P57-005", "P57-006", "P57-007"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P57 Real Dataset Candidate Regression Bridge Evidence",
        "app/services/real_dataset_candidate_regression_bridge.py",
        "scripts/run_real_dataset_candidate_regression_bridge.py",
        "tests/test_real_dataset_candidate_regression_bridge.py",
        "/tmp/opscat-real-dataset-candidate-regression-bridge-latest.md",
    ]:
        assert required in release
    assert "real_dataset_candidate_regression_bridge_smoke" in verify
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
