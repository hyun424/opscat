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


def test_p88_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p88-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p88-final-summary.md").read_text(encoding="utf-8")
    roadmap_index = Path("ROADMAP.md").read_text(encoding="utf-8")

    for required in ["P88-001", "P88-002", "P88-003", "P88-004", "P88-005", "P88-006", "P88-007", "P88-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P88 Bounded Local Supervisor Scheduler Contract Evidence",
        "app/services/bounded_local_supervisor_scheduler.py",
        "scripts/run_bounded_local_supervisor_scheduler.py",
        "tests/test_bounded_local_supervisor_scheduler.py",
        "evals/actions/p88_bounded_local_supervisor_scheduler.json",
        "/tmp/opscat-bounded-local-supervisor-scheduler-latest.md",
    ]:
        assert required in release
    assert "bounded_local_supervisor_scheduler_smoke" in verify
    assert "P88 active scope: Bounded Local Supervisor Scheduler Contract" in roadmap_index
    assert "P88 implemented as Bounded Local Supervisor Scheduler Contract evidence" in roadmap_index
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
