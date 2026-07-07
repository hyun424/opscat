from __future__ import annotations

from pathlib import Path


def test_p6_release_evidence_links_eval_demo_security_and_roadmap() -> None:
    text = Path("docs/release-evidence.md").read_text()

    for required in [
        "P6 Agentic Loop Evidence",
        "docs/operations/p6-ticket-roadmap.md",
        "docs/agentic-loop.md",
        "scripts/demo_agentic_loop.py",
        "scripts/run_agentic_evals.py",
        "/tmp/opscat-agentic-evals-latest.md",
        "docs/security-review-p6.md",
        "bash scripts/verify.sh --profile full",
    ]:
        assert required in text
    assert "does not claim production readiness" in text


def test_roadmap_marks_p6_and_p7_candidates() -> None:
    text = Path("ROADMAP.md").read_text()

    assert "P6 — Beta-grade agentic ops loop" in text
    assert "P7 candidates" in text
