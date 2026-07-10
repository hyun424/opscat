from pathlib import Path


def test_p99_release_evidence_documents_broad_matrix_and_boundaries() -> None:
    roadmap = Path("docs/operations/p99-ticket-roadmap.md").read_text(encoding="utf-8")
    review = Path("docs/operations/p99-plan-review.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p99-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    project_roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for ticket_number in range(1, 12):
        assert f"P99-{ticket_number:03d}" in roadmap
    for marker in (
        "52 families",
        "520 cases",
        "4,680",
        "140,400",
        "34.55%",
        "89.87%",
        "11.47%",
        "100% / 100%",
        "not literally exhaustive",
        "does not prove production",
    ):
        assert marker.lower() in summary.lower()
    assert "## P99 Comprehensive Operational Failure Matrix" in release
    assert "## P99 implemented" in project_roadmap
    assert "scripts/run_operational_scenario_matrix.py" in readme
    assert "operational_scenario_matrix_smoke" in verify
    assert "tests/test_p99_release_evidence.py" in verify
    assert "vendor-specific shell commands" in review


def test_p99_evidence_contains_no_secret_material() -> None:
    paths = (
        "docs/operations/p99-ticket-roadmap.md",
        "docs/operations/p99-plan-review.md",
        "docs/operations/p99-final-summary.md",
        "docs/release-evidence.md",
        "README.md",
    )
    rendered = "\n".join(Path(path).read_text(encoding="utf-8") for path in paths)
    for marker in ("nvapi-", "sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "actual-secret-value"):
        assert marker not in rendered
