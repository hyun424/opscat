from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-")


def test_p18a_ticket_roadmap_lists_realtime_reader_scope() -> None:
    text = Path("docs/operations/p18a-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P18A Ticket Roadmap — Realtime Source Reader",
        "P18A-001",
        "P18A-002",
        "P18A-003",
        "P18A-004",
        "P18A-005",
        "P18A-006",
        "P18A-007",
        "P18A-008",
        "No auth work",
        "No production mutation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p18a_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p18a-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P18A Final Summary — Realtime Source Reader",
        "P18A-001",
        "P18A-002",
        "P18A-003",
        "P18A-004",
        "P18A-005",
        "P18A-006",
        "P18A-007",
        "P18A-008",
        "app/services/realtime_source_reader.py",
        "scripts/replay_realtime_sources.py",
        "tests/test_realtime_source_reader.py",
        "source-native incremental",
        "no-auth/local-mock by default",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P18A Realtime Source Reader Evidence",
        "docs/operations/p18a-ticket-roadmap.md",
        "docs/operations/p18a-final-summary.md",
        "tests/test_realtime_source_reader.py",
        "tests/test_p18a_release_evidence.py",
        "/tmp/opscat-realtime-replay-latest.md",
    ]:
        assert required in release
    assert "P18A implemented as Realtime Source Reader evidence" in roadmap
    assert "realtime_source_replay_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
