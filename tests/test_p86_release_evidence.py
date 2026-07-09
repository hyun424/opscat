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


def test_p86_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p86-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p86-final-summary.md").read_text(encoding="utf-8")
    roadmap_index = Path("ROADMAP.md").read_text(encoding="utf-8")

    for required in ["P86-001", "P86-002", "P86-003", "P86-004", "P86-005", "P86-006", "P86-007", "P86-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P86 Resumable Local Supervisor Runner Evidence",
        "app/services/resumable_local_supervisor_runner.py",
        "scripts/run_resumable_local_supervisor_runner.py",
        "tests/test_resumable_local_supervisor_runner.py",
        "evals/actions/p86_resumable_local_supervisor_runner.json",
        "/tmp/opscat-resumable-local-supervisor-runner-latest.md",
    ]:
        assert required in release
    assert "resumable_local_supervisor_runner_smoke" in verify
    assert "P86 active scope: Resumable Local Supervisor Runner" in roadmap_index
    assert "P86 implemented as Resumable Local Supervisor Runner evidence" in roadmap_index
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
