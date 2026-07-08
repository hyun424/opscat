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


def test_p78_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p78-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p78-final-summary.md").read_text(encoding="utf-8")
    roadmap_index = Path("ROADMAP.md").read_text(encoding="utf-8")

    for required in ["P78-001", "P78-002", "P78-003", "P78-004", "P78-005", "P78-006", "P78-007", "P78-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P78 Runbook Simulation Tournament Evidence",
        "app/services/runbook_simulation_tournament.py",
        "scripts/run_runbook_simulation_tournament.py",
        "tests/test_runbook_simulation_tournament.py",
        "evals/runbooks/p78_runbook_candidates.json",
        "/tmp/opscat-runbook-simulation-tournament-latest.md",
    ]:
        assert required in release
    assert "runbook_simulation_tournament_smoke" in verify
    assert "P78 active scope: Runbook Simulation Tournament" in roadmap_index
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
