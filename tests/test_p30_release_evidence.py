from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "Bearer secret-token")


def test_p30_ticket_roadmap_lists_controlled_remediation_scope() -> None:
    text = Path("docs/operations/p30-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P30 Ticket Roadmap — Controlled Auto-remediation Policy and Simulation",
        "P30-001",
        "P30-002",
        "P30-003",
        "P30-004",
        "P30-005",
        "P30-006",
        "P30-007",
        "P30-008",
        "simulation/local-mock by default",
        "no production mutation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p30_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p30-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P30 Final Summary — Controlled Auto-remediation Policy and Simulation",
        "P30-001",
        "P30-002",
        "P30-003",
        "P30-004",
        "P30-005",
        "P30-006",
        "P30-007",
        "P30-008",
        "app/services/controlled_remediation.py",
        "scripts/run_controlled_remediation.py",
        "evals/remediation/p30_drills.json",
        "simulation-first controlled auto-remediation",
        "unsafe_auto_action_count: 0",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P30 Controlled Auto-remediation Policy and Simulation Evidence",
        "docs/operations/p30-ticket-roadmap.md",
        "docs/operations/p30-final-summary.md",
        "tests/test_controlled_remediation_policy.py",
        "tests/test_p30_release_evidence.py",
        "/tmp/opscat-controlled-remediation-latest.md",
    ]:
        assert required in release
    assert "P30 implemented as Controlled Auto-remediation Policy and Simulation evidence" in roadmap
    assert "controlled_remediation_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
