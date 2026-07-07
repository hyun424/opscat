from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-")


def test_p17_ticket_roadmap_lists_calibration_tickets() -> None:
    text = Path("docs/operations/p17-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P17 Ticket Roadmap — LLM Policy Calibration",
        "P17-001",
        "P17-002",
        "P17-003",
        "P17-004",
        "P17-005",
        "P17-006",
        "P17-007",
        "No auth work",
        "No production mutation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p17_final_summary_and_release_evidence_exist() -> None:
    summary = Path("docs/operations/p17-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P17 Final Summary — LLM Policy Calibration",
        "P17-001",
        "P17-002",
        "P17-003",
        "P17-004",
        "P17-005",
        "P17-006",
        "P17-007",
        "app/services/policy_calibrator.py",
        "tests/test_policy_calibrator.py",
        "bash scripts/verify.sh --profile full",
        "no-auth/local-mock by default",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P17 LLM Policy Calibration Evidence",
        "docs/operations/p17-ticket-roadmap.md",
        "docs/operations/p17-final-summary.md",
        "tests/test_policy_calibrator.py",
        "tests/test_p17_release_evidence.py",
        "/tmp/opscat-policy-calibration-latest.md",
    ]:
        assert required in release
    assert "P17 implemented as LLM Policy Calibration evidence" in roadmap
    assert "policy_calibration_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
