from pathlib import Path


def test_p103_release_evidence_documents_multi_step_results() -> None:
    roadmap = Path("docs/operations/p103-ticket-roadmap.md").read_text(encoding="utf-8")
    review = Path("docs/operations/p103-plan-review.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p103-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    project_roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for ticket_number in range(1, 13):
        assert f"P103-{ticket_number:03d}" in roadmap
    for marker in (
        "520 cases",
        "2,080 reported comparison trials",
        "67 external model decisions",
        "98.08%",
        "76.92%",
        "provider executed zero actions",
        "does not prove production",
    ):
        assert marker.lower() in summary.lower()
    assert "## P103 Multi-step LLM Diagnostic Episode" in release
    assert "## P103 implemented" in project_roadmap
    assert "scripts/run_llm_diagnostic_episode.py" in readme
    assert "llm_diagnostic_episode_smoke" in verify
    assert "tests/test_p103_release_evidence.py" in verify
    assert "LLM receives no action authority" in review


def test_p103_evidence_contains_no_secret_material() -> None:
    paths = (
        "docs/operations/p103-ticket-roadmap.md",
        "docs/operations/p103-plan-review.md",
        "docs/operations/p103-final-summary.md",
        "docs/release-evidence.md",
        "README.md",
    )
    rendered = "\n".join(Path(path).read_text(encoding="utf-8") for path in paths)
    for marker in ("nvapi-", "sk_live_", "xoxb-", "ghp_", "BEGIN PRIVATE KEY"):
        assert marker not in rendered
