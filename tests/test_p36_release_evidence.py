from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p36_ticket_roadmap_lists_approval_control_scope() -> None:
    text = Path("docs/operations/p36-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P36 Ticket Roadmap — Approval Control Plane",
        "P36-001",
        "P36-002",
        "P36-003",
        "P36-004",
        "P36-005",
        "P36-006",
        "P36-007",
        "P36-008",
        "no auth/session/user management work",
        "no live API calls",
        "no production mutation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p36_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p36-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P36 Final Summary — Approval Control Plane",
        "P36-001",
        "P36-002",
        "P36-003",
        "P36-004",
        "P36-005",
        "P36-006",
        "P36-007",
        "P36-008",
        "app/services/approval_control_plane.py",
        "scripts/run_approval_control_plane.py",
        "evals/approval/p36_profiles.json",
        "profile coverage",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P36 Approval Control Plane Evidence",
        "docs/operations/p36-ticket-roadmap.md",
        "docs/operations/p36-final-summary.md",
        "tests/test_approval_control_plane.py",
        "tests/test_p36_release_evidence.py",
        "/tmp/opscat-approval-control-plane-latest.md",
    ]:
        assert required in release
    assert "P36 active scope: Approval Control Plane" in roadmap
    assert "approval_control_plane_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
