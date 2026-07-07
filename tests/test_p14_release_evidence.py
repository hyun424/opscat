from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "secrets.")


def test_p14_final_summary_maps_tickets_to_artifacts() -> None:
    text = Path("docs/operations/p14-final-summary.md").read_text()
    for required in [
        "# OpsCat P14 Final Summary — LLM Judgment Adapter",
        "P14-001",
        "P14-002",
        "P14-003",
        "P14-004",
        "P14-005",
        "P14-006",
        "P14-007",
        "P14-008",
        "P14-009",
        "P14-010",
        "P14-011",
        "app/services/llm_judgment.py",
        "scripts/run_llm_judgment.py",
        "bash scripts/verify.sh --profile full",
        "no-auth/local-mock",
        "does not claim unattended production operation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p14_release_evidence_and_verify_include_llm_judgment() -> None:
    release = Path("docs/release-evidence.md").read_text()
    roadmap = Path("ROADMAP.md").read_text()
    verify = Path("scripts/verify.sh").read_text()
    for required in [
        "P14 LLM Judgment Adapter Evidence",
        "docs/operations/p14-ticket-roadmap.md",
        "docs/operations/p14-final-summary.md",
        "tests/test_llm_judgment.py",
        "tests/test_llm_judgment_cli.py",
        "tests/test_p14_release_evidence.py",
        "scripts/run_llm_judgment.py",
        "/tmp/opscat-llm-judgment-latest.md",
        "bash scripts/verify.sh --profile full",
    ]:
        assert required in release
    assert "P14 implemented as local/mock LLM Judgment Adapter evidence" in roadmap
    assert "llm_judgment_smoke" in verify
