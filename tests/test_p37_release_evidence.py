from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p37_ticket_roadmap_lists_config_hardening_scope() -> None:
    text = Path("docs/operations/p37-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P37 Ticket Roadmap — Open-source Config Hardening",
        "P37-001",
        "P37-002",
        "P37-003",
        "P37-004",
        "P37-005",
        "P37-006",
        "P37-007",
        "P37-008",
        "no reading or printing real `.env` values",
        "no live API calls",
        "no production mutation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p37_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p37-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P37 Final Summary — Open-source Config Hardening",
        "P37-001",
        "P37-002",
        "P37-003",
        "P37-004",
        "P37-005",
        "P37-006",
        "P37-007",
        "P37-008",
        "app/services/open_source_config_hardening.py",
        "scripts/run_open_source_config_hardening.py",
        "evals/config/p37_config_manifest.json",
        "safe default rate",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P37 Open-source Config Hardening Evidence",
        "docs/operations/p37-ticket-roadmap.md",
        "docs/operations/p37-final-summary.md",
        "tests/test_open_source_config_hardening.py",
        "tests/test_p37_release_evidence.py",
        "/tmp/opscat-open-source-config-hardening-latest.md",
    ]:
        assert required in release
    assert "P37 active scope: Open-source Config Hardening" in roadmap
    assert "open_source_config_hardening_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
