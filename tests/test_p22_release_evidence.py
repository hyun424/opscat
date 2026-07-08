from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-")


def test_p22_ticket_roadmap_lists_night_shift_scope() -> None:
    text = Path("docs/operations/p22-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P22 Ticket Roadmap — Night-shift Runtime Drill and SLA Scoring",
        "P22-001",
        "P22-002",
        "P22-003",
        "P22-004",
        "P22-005",
        "P22-006",
        "no-auth/local-mock",
        "no remediation execution",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p22_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p22-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P22 Final Summary — Night-shift Runtime Drill and SLA Scoring",
        "P22-001",
        "P22-002",
        "P22-003",
        "P22-004",
        "P22-005",
        "P22-006",
        "app/services/night_shift_drill.py",
        "scripts/run_night_shift_drill.py",
        "tests/test_night_shift_drill.py",
        "SLA",
        "safety_violation_count",
        "no-auth/local-mock by default",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P22 Night-shift Runtime Drill and SLA Scoring Evidence",
        "docs/operations/p22-ticket-roadmap.md",
        "docs/operations/p22-final-summary.md",
        "tests/test_night_shift_drill.py",
        "tests/test_p22_release_evidence.py",
        "/tmp/opscat-night-drill-latest.md",
    ]:
        assert required in release
    assert "P22 implemented as Night-shift Runtime Drill and SLA Scoring evidence" in roadmap
    assert "night_shift_drill_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
