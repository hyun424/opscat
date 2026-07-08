from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-")


def test_p24_ticket_roadmap_lists_proactive_scope() -> None:
    text = Path("docs/operations/p24-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P24 Ticket Roadmap — Proactive Risk Sentinel",
        "P24-001",
        "P24-002",
        "P24-003",
        "P24-004",
        "P24-005",
        "P24-006",
        "P24-007",
        "P24-008",
        "incident precursors",
        "no remediation execution",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p24_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p24-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P24 Final Summary — Proactive Risk Sentinel",
        "P24-001",
        "P24-002",
        "P24-003",
        "P24-004",
        "P24-005",
        "P24-006",
        "P24-007",
        "P24-008",
        "app/services/proactive_risk_sentinel.py",
        "scripts/run_proactive_risk_sentinel.py",
        "evals/proactive/seed/risk_windows.json",
        "ETA",
        "preventive_review",
        "no-auth/local-mock by default",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P24 Proactive Risk Sentinel Evidence",
        "docs/operations/p24-ticket-roadmap.md",
        "docs/operations/p24-final-summary.md",
        "tests/test_proactive_risk_sentinel.py",
        "tests/test_p24_release_evidence.py",
        "/tmp/opscat-proactive-risk-latest.md",
    ]:
        assert required in release
    assert "P24 implemented as Proactive Risk Sentinel evidence" in roadmap
    assert "proactive_risk_sentinel_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
