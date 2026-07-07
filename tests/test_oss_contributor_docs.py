"""Open-source contributor documentation gates for P5."""

from __future__ import annotations

from pathlib import Path

SECRET_REQUEST_PHRASES = (
    "paste your token",
    "paste production logs",
    "attach customer logs",
    "share your secret",
)


def test_contributing_guide_explains_safe_local_workflow() -> None:
    path = Path("CONTRIBUTING.md")

    assert path.exists()
    text = path.read_text()
    for required in [
        "# Contributing to OpsCat",
        "make quickstart",
        "make verify",
        "scripts/run_evals.py",
        "scripts/run_connector_evals.py",
        "Lore commit protocol",
        "No production credentials",
        "auth is deferred",
        "local/mock",
    ]:
        assert required in text
    assert all(phrase not in text.lower() for phrase in SECRET_REQUEST_PHRASES)


def test_roadmap_links_p5_and_marks_auth_deferred() -> None:
    path = Path("ROADMAP.md")

    assert path.exists()
    text = path.read_text()
    for required in [
        "# OpsCat Roadmap",
        "P4 complete",
        "P5 active",
        "docs/operations/p5-ticket-roadmap.md",
        "auth deferred",
        "P6 candidates",
    ]:
        assert required in text


def test_issue_templates_are_safe_for_public_oss_usage() -> None:
    template_dir = Path(".github/ISSUE_TEMPLATE")
    expected = {
        "bug_report.md",
        "connector_request.md",
        "eval_scenario.md",
        "safety_concern.md",
    }

    assert template_dir.exists()
    actual = {path.name for path in template_dir.glob("*.md")}
    assert expected.issubset(actual)
    combined = "\n".join((template_dir / name).read_text() for name in expected)
    for required in [
        "Do not include secrets",
        "Do not paste customer logs",
        "local/mock",
    ]:
        assert required in combined
    assert all(phrase not in combined.lower() for phrase in SECRET_REQUEST_PHRASES)
