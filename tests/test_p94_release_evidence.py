from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = (
    "sk_live_",
    "xoxb-",
    "ghp_",
    "sntrys_",
    "BEGIN PRIVATE KEY",
    "prod-token",
    "nvapi-",
    "actual-secret-value",
    "Authorization",
    "Bearer",
)


def test_p94_docs_readme_release_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p94-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p94-final-summary.md").read_text(encoding="utf-8")
    roadmap_index = Path("ROADMAP.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    portfolio_demo = Path("docs/portfolio-demo.md").read_text(encoding="utf-8")
    transcript_demo = Path("docs/operator-transcript-demo.md").read_text(encoding="utf-8")

    for required in ["P94-001", "P94-002", "P94-003", "P94-004", "P94-005", "P94-006", "P94-007"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P94 Operator Transcript Demo / Human-like Incident Response Walkthrough",
        "app/services/operator_transcript_demo.py",
        "scripts/run_operator_transcript_demo.py",
        "tests/test_operator_transcript_demo.py",
        "tests/test_p94_release_evidence.py",
        "evals/actions/p94_operator_transcript_demo.json",
        "/tmp/opscat-operator-transcript-demo-latest.md",
    ]:
        assert required in release
    assert "operator_transcript_demo_smoke" in verify
    assert "tests/test_p94_release_evidence.py" in verify
    assert "P94 active scope: Operator Transcript Demo / Human-like Incident Response Walkthrough" in roadmap_index
    assert "P94 implemented as Operator Transcript Demo evidence" in roadmap_index
    assert "scripts/run_operator_transcript_demo.py" in readme
    assert "docs/operator-transcript-demo.md" in readme
    assert "scenarios=4 transcript_steps>=40 hypotheses>=12 executions=0" in readme
    assert "best quick demo for reviewers" in portfolio_demo
    assert "agentic reasoning with evidence but no production action" in transcript_demo
    assert "local/mock-only" in transcript_demo
    assert "not production autonomy" in release
    assert all(marker not in release + roadmap + summary + readme + transcript_demo for marker in SECRET_MARKERS)
