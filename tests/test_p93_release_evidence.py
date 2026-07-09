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


def test_p93_docs_readme_release_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p93-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p93-final-summary.md").read_text(encoding="utf-8")
    roadmap_index = Path("ROADMAP.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    portfolio_demo = Path("docs/portfolio-demo.md").read_text(encoding="utf-8")
    operator_walkthrough = Path("docs/operator-walkthrough.md").read_text(encoding="utf-8")
    architecture = Path("docs/architecture.md").read_text(encoding="utf-8")

    for required in ["P93-001", "P93-002", "P93-003", "P93-004", "P93-005", "P93-006", "P93-007"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P93 Portfolio Demo Narrative & Operator Walkthrough Evidence",
        "app/services/portfolio_demo_pack.py",
        "scripts/run_portfolio_demo_pack.py",
        "tests/test_portfolio_demo_pack.py",
        "tests/test_p93_release_evidence.py",
        "evals/actions/p93_portfolio_demo_pack.json",
        "/tmp/opscat-portfolio-demo-pack-latest.md",
    ]:
        assert required in release
    assert "portfolio_demo_pack_smoke" in verify
    assert "tests/test_p93_release_evidence.py" in verify
    assert "P93 active scope: Portfolio Demo Narrative & Operator Walkthrough Evidence" in roadmap_index
    assert "P93 implemented as Portfolio Demo Narrative evidence" in roadmap_index
    assert "agentic AI incident-response/operator-replacement" in readme
    assert "uv run --no-sync --extra dev python scripts/run_portfolio_demo_pack.py" in readme
    assert "local/mock-only" in readme
    assert "docs/operator-walkthrough.md" in readme
    assert "walkthrough_steps>=8 proof_points>=6 commands>=3 executions=0" in portfolio_demo
    assert "observe" in operator_walkthrough
    assert "improve" in operator_walkthrough
    assert "P93 portfolio demo architecture narrative" in architecture
    assert "not production autonomy" in release
    assert all(marker not in release + roadmap + summary + readme for marker in SECRET_MARKERS)
