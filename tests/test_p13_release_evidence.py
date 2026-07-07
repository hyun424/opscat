from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "secrets.")


def test_p13_final_summary_maps_tickets_to_artifacts() -> None:
    text = Path("docs/operations/p13-final-summary.md").read_text()
    for required in [
        "# OpsCat P13 Final Summary — LLM Context Builder",
        "P13-001",
        "P13-002",
        "P13-003",
        "P13-004",
        "P13-005",
        "P13-006",
        "P13-007",
        "P13-008",
        "P13-009",
        "P13-010",
        "P13-011",
        "app/services/llm_context_builder.py",
        "scripts/build_llm_context.py",
        "bash scripts/verify.sh --profile full",
        "no-auth/local-mock",
        "does not claim unattended production operation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p13_release_evidence_and_verify_include_llm_context_builder() -> None:
    release = Path("docs/release-evidence.md").read_text()
    roadmap = Path("ROADMAP.md").read_text()
    verify = Path("scripts/verify.sh").read_text()
    for required in [
        "P13 LLM Context Builder Evidence",
        "docs/operations/p13-ticket-roadmap.md",
        "docs/operations/p13-final-summary.md",
        "tests/test_llm_context_builder.py",
        "tests/test_llm_context_cli.py",
        "tests/test_p13_release_evidence.py",
        "scripts/build_llm_context.py",
        "/tmp/opscat-llm-context-latest.md",
        "bash scripts/verify.sh --profile full",
    ]:
        assert required in release
    assert "P13 implemented as local/mock LLM Context Builder evidence" in roadmap
    assert "llm_context_smoke" in verify
