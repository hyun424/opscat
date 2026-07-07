"""Open-source quickstart documentation and command contract for P5."""

from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY")


def test_env_example_is_safe_and_local_only() -> None:
    env_example = Path(".env.example")

    assert env_example.exists()
    text = env_example.read_text()
    assert "OPSCAT_MODE=local-mock" in text
    assert "DATABASE_URL=sqlite:///./opscat.db" in text
    assert "REPORT_DIR=data/mock_reports" in text
    assert "Do not use production credentials" in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_makefile_exposes_oss_quickstart_targets() -> None:
    makefile = Path("Makefile")

    assert makefile.exists()
    text = makefile.read_text()
    for target in ["install", "test", "demo", "evals", "verify", "run", "quickstart"]:
        assert f"{target}:" in text
    assert "uv run --no-sync --extra dev python scripts/demo.py" in text
    assert "uv run --no-sync --extra dev pytest -q" in text
    assert "bash scripts/verify.sh" in text
    assert "scripts/run_evals.py" in text
    assert "scripts/run_connector_evals.py" in text


def test_readme_has_clone_to_demo_open_source_quickstart() -> None:
    readme = Path("README.md").read_text()

    for required in [
        "## Open-source quickstart",
        "make quickstart",
        "make demo",
        "make verify",
        ".env.example",
        "No auth setup is required",
        "Do not use production credentials",
        "local-header demo identity",
    ]:
        assert required in readme
