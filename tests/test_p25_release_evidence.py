from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-")


def test_p25_ticket_roadmap_lists_calibration_scope() -> None:
    text = Path("docs/operations/p25-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P25 Ticket Roadmap — Proactive Signal Corpus Expansion and Calibration",
        "P25-001",
        "P25-002",
        "P25-003",
        "P25-004",
        "P25-005",
        "P25-006",
        "P25-007",
        "at least 100 deterministic local/mock windows",
        "ETA/route/confidence/action safety",
        "no remediation execution",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p25_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p25-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P25 Final Summary — Proactive Signal Corpus Expansion and Calibration",
        "P25-001",
        "P25-002",
        "P25-003",
        "P25-004",
        "P25-005",
        "P25-006",
        "P25-007",
        "100+ proactive windows",
        "30+ risk types",
        "scripts/run_proactive_calibration.py",
        "tests/test_p25_proactive_corpus_calibration.py",
        "route_mismatch_count=0",
        "eta_out_of_range_count=0",
        "no-auth/local-mock by default",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P25 Proactive Signal Corpus Expansion and Calibration Evidence",
        "docs/operations/p25-ticket-roadmap.md",
        "docs/operations/p25-final-summary.md",
        "tests/test_p25_proactive_corpus_calibration.py",
        "tests/test_p25_release_evidence.py",
        "/tmp/opscat-proactive-calibration-latest.md",
    ]:
        assert required in release
    assert "P25 implemented as Proactive Signal Corpus Expansion and Calibration evidence" in roadmap
    assert "proactive_calibration_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
