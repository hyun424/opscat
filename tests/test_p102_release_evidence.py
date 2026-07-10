from pathlib import Path


def test_p102_release_evidence_documents_llm_tool_planner_results() -> None:
    roadmap = Path("docs/operations/p102-ticket-roadmap.md").read_text(encoding="utf-8")
    review = Path("docs/operations/p102-plan-review.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p102-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    project_roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for ticket_number in range(1, 13):
        assert f"P102-{ticket_number:03d}" in roadmap
    for marker in (
        "208 decisions",
        "94.23%",
        "48 live decisions",
        "zero unsafe tools",
        "does not prove production",
    ):
        assert marker.lower() in summary.lower()
    assert "## P102 LLM Diagnostic Tool Planner" in release
    assert "## P102 implemented" in project_roadmap
    assert "scripts/run_llm_tool_planner_evaluation.py" in readme
    assert "llm_tool_planner_evaluation_smoke" in verify
    assert "tests/test_p102_release_evidence.py" in verify
    assert "cannot execute a tool or action" in review


def test_p102_evidence_contains_no_secret_material() -> None:
    paths = (
        "docs/operations/p102-ticket-roadmap.md",
        "docs/operations/p102-plan-review.md",
        "docs/operations/p102-final-summary.md",
        "docs/release-evidence.md",
        "README.md",
    )
    rendered = "\n".join(Path(path).read_text(encoding="utf-8") for path in paths)
    for marker in ("nvapi-", "sk_live_", "xoxb-", "ghp_", "BEGIN PRIVATE KEY"):
        assert marker not in rendered
