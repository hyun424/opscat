from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "secrets.")


def test_p8_final_summary_maps_all_tickets_to_artifacts_and_verification() -> None:
    path = Path("docs/operations/p8-final-summary.md")

    assert path.exists()
    text = path.read_text()
    for required in [
        "# OpsCat P8 Final Summary — AI Incident Responder War Room",
        "P8-001",
        "P8-002",
        "P8-003",
        "P8-004",
        "P8-005",
        "P8-006",
        "P8-007",
        "P8-008",
        "P8-009",
        "P8-010",
        "docs/operations/p8-demo-script.md",
        "docs/security-review-p8.md",
        "bash scripts/verify.sh --profile full",
        "no-auth/local-mock",
        "does not claim unattended production operation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p8_release_evidence_and_roadmap_expose_reviewer_commands() -> None:
    release = Path("docs/release-evidence.md").read_text()
    roadmap = Path("ROADMAP.md").read_text()

    for required in [
        "P8 AI Incident Responder War Room Evidence",
        "docs/operations/p8-ticket-roadmap.md",
        "docs/operations/p8-final-summary.md",
        "docs/operations/p8-demo-script.md",
        "docs/security-review-p8.md",
        "tests/test_p8_demo.py",
        "tests/test_p8_security_docs.py",
        "tests/test_p8_release_evidence.py",
        "bash scripts/verify.sh --profile full",
        "does not claim unattended production operation",
    ]:
        assert required in release

    assert "P8 implemented as local/mock AI Incident Responder War Room evidence" in roadmap
    assert "no-auth/local-mock" in roadmap
    assert all(marker not in release for marker in SECRET_MARKERS)
