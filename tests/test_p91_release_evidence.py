from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = (
    "sk_live_",
    "xoxb-",
    "ghp_",
    "sntrys_",
    "BEGIN PRIVATE KEY",
    "prod-token",
    "nvapi-",
    "actual-secret-value",
    "Authorization",
    "Bearer",
)


def test_p91_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p91-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p91-final-summary.md").read_text(encoding="utf-8")
    roadmap_index = Path("ROADMAP.md").read_text(encoding="utf-8")

    for required in ["P91-001", "P91-002", "P91-003", "P91-004", "P91-005", "P91-006", "P91-007", "P91-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P91 Readiness Gap Remediation Planner Evidence",
        "app/services/readiness_gap_remediation_planner.py",
        "scripts/run_readiness_gap_remediation_planner.py",
        "tests/test_readiness_gap_remediation_planner.py",
        "evals/actions/p91_readiness_gap_remediation_planner.json",
        "/tmp/opscat-readiness-gap-remediation-planner-latest.md",
    ]:
        assert required in release
    assert "readiness_gap_remediation_planner_smoke" in verify
    assert "P91 active scope: Readiness Gap Remediation Planner" in roadmap_index
    assert "P91 implemented as Readiness Gap Remediation Planner evidence" in roadmap_index
    assert "roadmap/planning artifact" in release
    assert "not production autonomy" in release
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
