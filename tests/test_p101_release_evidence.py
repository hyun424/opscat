from pathlib import Path


def test_p101_release_evidence_documents_tool_runtime_results() -> None:
    roadmap = Path("docs/operations/p101-ticket-roadmap.md").read_text(encoding="utf-8")
    review = Path("docs/operations/p101-plan-review.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p101-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    project_roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for ticket_number in range(1, 13):
        assert f"P101-{ticket_number:03d}" in roadmap
    for marker in (
        "4,680 trials",
        "118,580",
        "56.54%",
        "1.35%",
        "94.23%",
        "Relevant-tool discovery: **100%**",
        "does not prove generalization",
    ):
        assert marker.lower() in summary.lower()
    assert "## P101 Tool-Using Hypothesis Investigator" in release
    assert "## P101 implemented" in project_roadmap
    assert "scripts/run_tool_investigation_benchmark.py" in readme
    assert "tool_investigation_benchmark_smoke" in verify
    assert "tests/test_p101_release_evidence.py" in verify
    assert "expected diagnostic surface is scorer-only" in review


def test_p101_evidence_contains_no_secret_material() -> None:
    paths = (
        "docs/operations/p101-ticket-roadmap.md",
        "docs/operations/p101-plan-review.md",
        "docs/operations/p101-final-summary.md",
        "docs/release-evidence.md",
        "README.md",
    )
    rendered = "\n".join(Path(path).read_text(encoding="utf-8") for path in paths)
    for marker in ("nvapi-", "sk_live_", "xoxb-", "ghp_", "BEGIN PRIVATE KEY"):
        assert marker not in rendered
