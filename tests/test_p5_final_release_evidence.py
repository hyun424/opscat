"""P5 final release evidence closure contract."""

from __future__ import annotations

from pathlib import Path

COMPLETED_TICKETS = [
    "P5-001",
    "P5-002",
    "P5-003",
    "P5-004",
    "P5-005",
    "P5-006",
    "P5-007",
    "P5-008",
    "P5-009",
    "P5-010",
    "P5-011",
    "P5-012",
    "P5-013",
    "P5-014",
    "P5-015",
    "P5-016",
    "P5-017",
    "P5-018",
]


def test_release_evidence_has_p5_final_green_summary() -> None:
    text = Path("docs/release-evidence.md").read_text()

    assert "P5 final release evidence" in text
    assert "bash scripts/verify.sh --profile full" in text
    assert "Verification complete (full)" in text
    assert "auth remains deferred" in text
    for ticket in COMPLETED_TICKETS:
        assert ticket in text


def test_integration_verification_records_p5_pass_and_boundaries() -> None:
    text = Path("docs/integration-verification.md").read_text()

    assert "P5 final verification" in text
    assert "bash scripts/verify.sh --profile full" in text
    assert "PASS" in text
    assert "auth remains deferred" in text
    assert "local/mock" in text


def test_p5_roadmaps_mark_all_tickets_done() -> None:
    for path in [Path("docs/operations/p5-ticket-roadmap.md"), Path(".omx/plans/opscat-p5-ticket-roadmap.md")]:
        text = path.read_text()
        for ticket in COMPLETED_TICKETS:
            assert f"### {ticket} ✅" in text
        assert "P5 final release evidence" in text
