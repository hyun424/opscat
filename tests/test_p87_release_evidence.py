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


def test_p87_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p87-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p87-final-summary.md").read_text(encoding="utf-8")
    roadmap_index = Path("ROADMAP.md").read_text(encoding="utf-8")

    for required in ["P87-001", "P87-002", "P87-003", "P87-004", "P87-005", "P87-006", "P87-007", "P87-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P87 Supervisor Run Report Artifact Evidence",
        "app/services/supervisor_run_report_artifact.py",
        "scripts/run_supervisor_run_report_artifact.py",
        "tests/test_supervisor_run_report_artifact.py",
        "evals/actions/p87_supervisor_run_report_artifact.json",
        "/tmp/opscat-supervisor-run-report-artifact-latest.md",
    ]:
        assert required in release
    assert "supervisor_run_report_artifact_smoke" in verify
    assert "P87 active scope: Supervisor Run Report Artifact" in roadmap_index
    assert "P87 implemented as Supervisor Run Report Artifact evidence" in roadmap_index
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
