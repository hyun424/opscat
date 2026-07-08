from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-")


def test_p23_ticket_roadmap_lists_corpus_scope() -> None:
    text = Path("docs/operations/p23-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P23 Ticket Roadmap — Incident Scenario Corpus Expansion",
        "P23-001",
        "P23-002",
        "P23-003",
        "P23-004",
        "P23-005",
        "P23-006",
        "At least 60 total cases",
        "Connection pool has at least 8 focused scenarios",
        "no remediation execution",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p23_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p23-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P23 Final Summary — Incident Scenario Corpus Expansion",
        "P23-001",
        "P23-002",
        "P23-003",
        "P23-004",
        "P23-005",
        "P23-006",
        "60 scenarios",
        "connection_pool",
        "tests/test_p23_scenario_corpus.py",
        "no-auth/local-mock by default",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P23 Incident Scenario Corpus Expansion Evidence",
        "docs/operations/p23-ticket-roadmap.md",
        "docs/operations/p23-final-summary.md",
        "tests/test_p23_scenario_corpus.py",
        "tests/test_p23_release_evidence.py",
    ]:
        assert required in release
    assert "P23 implemented as Incident Scenario Corpus Expansion evidence" in roadmap
    assert "tests/test_p23_release_evidence.py" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
