from pathlib import Path


def test_p96_release_evidence_documents_real_read_only_prometheus_boundary() -> None:
    roadmap = Path("docs/operations/p96-ticket-roadmap.md").read_text(encoding="utf-8")
    review = Path("docs/operations/p96-plan-review.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p96-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    project_roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")

    for ticket in ("P96-001", "P96-002", "P96-003", "P96-004", "P96-005", "P96-006", "P96-007", "P96-008"):
        assert ticket in roadmap
    for marker in (
        "configured endpoint",
        "host allowlist",
        "GET-only",
        "query budgets",
        "normalized evidence",
        "P97",
    ):
        assert marker in summary
    assert "request-controlled" in review
    assert "## P96 Real Prometheus Read-only Shadow Connector" in release
    assert "## P96 implemented" in project_roadmap
    assert "scripts/probe_prometheus.py" in readme
    assert "OPSCAT_PROMETHEUS_BASE_URL" in readme
    assert "fixture mode" in readme.lower()
    assert "no remediation" in summary.lower()


def test_p96_evidence_contains_no_secret_material() -> None:
    paths = (
        "docs/operations/p96-ticket-roadmap.md",
        "docs/operations/p96-plan-review.md",
        "docs/operations/p96-final-summary.md",
        "docs/release-evidence.md",
        "README.md",
    )
    rendered = "\n".join(Path(path).read_text(encoding="utf-8") for path in paths)
    for marker in ("nvapi-", "sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "actual-secret-value"):
        assert marker not in rendered

