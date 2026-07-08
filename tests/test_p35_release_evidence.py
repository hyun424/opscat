from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p35_ticket_roadmap_lists_shadow_scope() -> None:
    text = Path("docs/operations/p35-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P35 Ticket Roadmap — Incident Shadow Mode",
        "P35-001",
        "P35-002",
        "P35-003",
        "P35-004",
        "P35-005",
        "P35-006",
        "P35-007",
        "P35-008",
        "no live API calls",
        "no production mutation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p35_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p35-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P35 Final Summary — Incident Shadow Mode",
        "P35-001",
        "P35-002",
        "P35-003",
        "P35-004",
        "P35-005",
        "P35-006",
        "P35-007",
        "P35-008",
        "app/services/incident_shadow_mode.py",
        "scripts/run_incident_shadow_mode.py",
        "evals/shadow/p35_shadow_cases.json",
        "expected_route_match_rate",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P35 Incident Shadow Mode Evidence",
        "docs/operations/p35-ticket-roadmap.md",
        "docs/operations/p35-final-summary.md",
        "tests/test_incident_shadow_mode.py",
        "tests/test_p35_release_evidence.py",
        "/tmp/opscat-incident-shadow-mode-latest.md",
    ]:
        assert required in release
    assert "P35 implemented as Incident Shadow Mode evidence" in roadmap
    assert "incident_shadow_mode_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
