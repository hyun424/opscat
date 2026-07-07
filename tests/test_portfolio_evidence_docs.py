"""Portfolio evidence documentation gates for P4."""

from __future__ import annotations

from pathlib import Path


def test_p4_eval_report_documents_reproducible_evidence() -> None:
    report = Path("docs/eval-report.md")

    assert report.exists()
    text = report.read_text()
    for required in [
        "# OpsCat P4 Eval Evidence Report",
        "## Operator replacement claim",
        "## Golden incident evals",
        "## Connector safety evals",
        "## Dashboard browser-contract E2E",
        "## Reproduce locally",
        "## Known limits",
    ]:
        assert required in text
    for command in [
        "python scripts/run_evals.py --output-json /tmp/opscat-evals.json --output-md /tmp/opscat-evals.md",
        "python scripts/run_connector_evals.py --output-json /tmp/opscat-connector-evals.json --output-md /tmp/opscat-connector-evals.md",
        "bash scripts/verify.sh",
    ]:
        assert command in text
    assert "23/23" in text
    assert "7/7" in text
    assert "local/mock" in text
    assert "no real Slack/GitHub/Sentry side effects" in text


def test_readme_points_reviewers_to_eval_evidence() -> None:
    readme = Path("README.md").read_text()

    assert "docs/eval-report.md" in readme
    assert "Connector evals" in readme
    assert "scripts/run_connector_evals.py" in readme


def test_p6_portfolio_demo_docs_explain_agentic_loop_without_overclaiming() -> None:
    readme = Path("README.md").read_text()
    demo = Path("docs/portfolio-demo.md").read_text()
    loop = Path("docs/agentic-loop.md").read_text()

    for text in [readme, demo, loop]:
        assert "observe" in text.lower()
        assert "correlate" in text.lower()
        assert "diagnose" in text.lower()
        assert "plan" in text.lower()
        assert "risk" in text.lower()
        assert "verify" in text.lower()
    assert "scripts/demo_agentic_loop.py" in readme
    assert "unattended production mutation" in readme
    assert "local/mock beta demo only" in demo
