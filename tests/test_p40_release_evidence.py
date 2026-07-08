from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p40_ticket_roadmap_lists_readiness_scope() -> None:
    text = Path("docs/operations/p40-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P40 Ticket Roadmap — Production-readiness Milestone Bundle",
        "P40-001",
        "P40-002",
        "P40-003",
        "P40-004",
        "P40-005",
        "P40-006",
        "P40-007",
        "P40-008",
        "does not claim unattended production operation",
        "does not enable production autopilot",
        "no live API calls",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p40_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p40-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P40 Final Summary — Production-readiness Milestone Bundle",
        "P40-001",
        "P40-002",
        "P40-003",
        "P40-004",
        "P40-005",
        "P40-006",
        "P40-007",
        "P40-008",
        "app/services/production_readiness_milestone.py",
        "scripts/run_production_readiness_milestone.py",
        "evals/readiness/p40_sources.json",
        "production autopilot ready",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P40 Production-readiness Milestone Bundle Evidence",
        "docs/operations/p40-ticket-roadmap.md",
        "docs/operations/p40-final-summary.md",
        "tests/test_production_readiness_milestone.py",
        "tests/test_p40_release_evidence.py",
        "/tmp/opscat-production-readiness-milestone-latest.md",
    ]:
        assert required in release
    assert "P40 active scope: Production-readiness Milestone Bundle" in roadmap
    assert "production_readiness_milestone_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
