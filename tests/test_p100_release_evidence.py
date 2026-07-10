from pathlib import Path


def test_p100_release_evidence_documents_stateful_results_and_boundaries() -> None:
    roadmap = Path("docs/operations/p100-ticket-roadmap.md").read_text(encoding="utf-8")
    review = Path("docs/operations/p100-plan-review.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p100-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    project_roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for ticket_number in range(1, 13):
        assert f"P100-{ticket_number:03d}" in roadmap
    for marker in (
        "6,240 trials",
        "183,990",
        "56.47%",
        "34.55%",
        "39.42%",
        "2.88%",
        "100% recall",
        "synthetic",
        "does not prove",
    ):
        assert marker.lower() in summary.lower()
    assert "## P100 Stateful Multi-step Incident Investigator" in release
    assert "## P100 implemented" in project_roadmap
    assert "scripts/run_stateful_incident_investigator.py" in readme
    assert "stateful_incident_investigator_smoke" in verify
    assert "tests/test_p100_release_evidence.py" in verify
    assert "scorer-only" in review.lower()


def test_p100_evidence_contains_no_secret_material() -> None:
    paths = (
        "docs/operations/p100-ticket-roadmap.md",
        "docs/operations/p100-plan-review.md",
        "docs/operations/p100-final-summary.md",
        "docs/release-evidence.md",
        "README.md",
    )
    rendered = "\n".join(Path(path).read_text(encoding="utf-8") for path in paths)
    for marker in (
        "nvapi-",
        "sk_live_",
        "xoxb-",
        "ghp_",
        "sntrys_",
        "BEGIN PRIVATE KEY",
        "actual-secret-value",
    ):
        assert marker not in rendered
