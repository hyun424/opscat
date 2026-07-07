"""P6 release evidence and roadmap gates."""

from __future__ import annotations

from pathlib import Path


def test_p6_release_evidence_links_eval_demo_security_and_boundaries() -> None:
    text = Path("docs/release-evidence.md").read_text()

    for required in [
        "## P6 beta-grade agentic loop evidence",
        "scripts/run_agentic_evals.py",
        "scripts/demo_agentic_loop.py",
        "docs/security-review-p6.md",
        "docs/agentic-loop.md",
        "docs/portfolio-demo.md",
        "/tmp/opscat-agentic-evals-latest.md",
        "observe → correlate → diagnose → plan → risk → act → verify",
        "No production credentials",
        "not production-ready",
    ]:
        assert required in text


def test_roadmap_marks_p6_lane_e_evidence_and_p7_candidates() -> None:
    text = Path("ROADMAP.md").read_text()

    assert "P6 evidence lane complete" in text
    assert "docs/operations/p6-ticket-roadmap.md" in text
    assert "P7 candidates" in text
    assert "production auth" in text


def test_changelog_records_p6_eval_demo_docs_package() -> None:
    text = Path("CHANGELOG.md").read_text()

    assert "P6 eval/demo/docs evidence package" in text
    assert "run_agentic_evals.py" in text
    assert "demo_agentic_loop.py" in text
