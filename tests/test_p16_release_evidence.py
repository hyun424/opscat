from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-")


def test_p16_final_summary_maps_tickets_to_artifacts() -> None:
    text = Path("docs/operations/p16-final-summary.md").read_text()
    for required in [
        "# OpsCat P16 Final Summary — LLM Provider Evaluation Runner",
        "P16-001",
        "P16-002",
        "P16-003",
        "P16-004",
        "P16-005",
        "P16-006",
        "P16-007",
        "app/services/llm_provider_evaluation.py",
        "scripts/run_llm_provider_eval.py",
        "bash scripts/verify.sh --profile full",
        "no-auth/local-mock by default",
        "does not claim unattended production operation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p16_release_evidence_and_verify_include_provider_eval() -> None:
    release = Path("docs/release-evidence.md").read_text()
    roadmap = Path("ROADMAP.md").read_text()
    verify = Path("scripts/verify.sh").read_text()
    for required in [
        "P16 LLM Provider Evaluation Evidence",
        "docs/operations/p16-ticket-roadmap.md",
        "docs/operations/p16-final-summary.md",
        "tests/test_llm_provider_evaluation.py",
        "tests/test_p16_release_evidence.py",
        "scripts/run_llm_provider_eval.py",
        "/tmp/opscat-llm-provider-eval-latest.md",
        "bash scripts/verify.sh --profile full",
    ]:
        assert required in release
    assert "P16 implemented as LLM Provider Evaluation Runner evidence" in roadmap
    assert "llm_provider_eval_smoke" in verify
