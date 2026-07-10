from pathlib import Path


def test_p97_release_evidence_documents_causal_scope_and_measured_results() -> None:
    roadmap = Path("docs/operations/p97-ticket-roadmap.md").read_text(encoding="utf-8")
    review = Path("docs/operations/p97-plan-review.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p97-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    project_roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for ticket in ("P97-001", "P97-002", "P97-003", "P97-004", "P97-005", "P97-006", "P97-007", "P97-008", "P97-009"):
        assert ticket in roadmap
    for marker in (
        "120",
        "1,080",
        "64,800",
        "no_action",
        "human_runbook",
        "opscat",
        "0.275",
        "44.17%",
        "90.0%",
        "synthetic local fault lab",
        "not production",
    ):
        assert marker.lower() in summary.lower()
    assert "## P97 Causal Remediation Benchmark" in release
    assert "## P97 implemented" in project_roadmap
    assert "scripts/run_causal_remediation_benchmark.py" in readme
    assert "--full-matrix" in readme
    assert "causal_remediation_benchmark_smoke" in verify
    assert "tests/test_p97_release_evidence.py" in verify
    assert "hidden truth" in review.lower()


def test_p97_evidence_contains_no_secret_or_production_claim() -> None:
    paths = (
        "docs/operations/p97-ticket-roadmap.md",
        "docs/operations/p97-plan-review.md",
        "docs/operations/p97-final-summary.md",
        "docs/release-evidence.md",
        "README.md",
    )
    rendered = "\n".join(Path(path).read_text(encoding="utf-8") for path in paths)
    for marker in ("nvapi-", "sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "actual-secret-value"):
        assert marker not in rendered
    summary = Path("docs/operations/p97-final-summary.md").read_text(encoding="utf-8").lower()
    assert "does not prove production remediation effectiveness" in summary
