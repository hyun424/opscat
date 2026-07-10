from pathlib import Path


def test_p98_release_evidence_documents_selector_comparison_boundary() -> None:
    roadmap = Path("docs/operations/p98-ticket-roadmap.md").read_text(encoding="utf-8")
    review = Path("docs/operations/p98-plan-review.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p98-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    project_roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for ticket in ("P98-001", "P98-002", "P98-003", "P98-004", "P98-005", "P98-006", "P98-007"):
        assert ticket in roadmap
    for marker in ("3 selectors", "120 cases", "360 OpsCat decision arms", "blind", "44.17%", "12.50%", "hard safety gate", "does not prove production"):
        assert marker.lower() in summary.lower()
    assert "## P98 Selector Comparison" in release
    assert "## P98 implemented" in project_roadmap
    assert "scripts/run_selector_comparison.py" in readme
    assert "selector_comparison_smoke" in verify
    assert "tests/test_p98_release_evidence.py" in verify
    assert "hidden truth" in review.lower()


def test_p98_evidence_contains_no_secret_material() -> None:
    paths = (
        "docs/operations/p98-ticket-roadmap.md",
        "docs/operations/p98-plan-review.md",
        "docs/operations/p98-final-summary.md",
        "docs/release-evidence.md",
        "README.md",
    )
    rendered = "\n".join(Path(path).read_text(encoding="utf-8") for path in paths)
    for marker in ("nvapi-", "sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "actual-secret-value"):
        assert marker not in rendered
