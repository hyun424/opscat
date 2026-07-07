from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "secrets.")


def test_p15_final_summary_maps_tickets_to_artifacts() -> None:
    text = Path("docs/operations/p15-final-summary.md").read_text()
    for required in [
        "# OpsCat P15 Final Summary — NVIDIA LLM Provider Opt-in",
        "P15-001",
        "P15-002",
        "P15-003",
        "P15-004",
        "P15-005",
        "P15-006",
        "P15-007",
        "app/services/llm_judgment.py",
        "scripts/run_llm_judgment.py",
        "nvidia/nemotron-3-ultra-550b-a55b",
        "NVIDIA_API_KEY",
        "no-auth/local-mock by default",
        "does not claim unattended production operation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p15_release_evidence_and_cli_document_nvidia_provider() -> None:
    release = Path("docs/release-evidence.md").read_text()
    roadmap = Path("ROADMAP.md").read_text()
    cli = Path("scripts/run_llm_judgment.py").read_text()
    for required in [
        "P15 NVIDIA LLM Provider Opt-in Evidence",
        "docs/operations/p15-ticket-roadmap.md",
        "docs/operations/p15-final-summary.md",
        "tests/test_nvidia_llm_provider.py",
        "tests/test_p15_release_evidence.py",
        "--provider nvidia",
        "OPSCAT_NVIDIA_MODEL",
        "NVIDIA_API_KEY",
        "nvidia/nemotron-3-ultra-550b-a55b",
    ]:
        assert required in release
    assert "P15 implemented as opt-in NVIDIA LLM Provider evidence" in roadmap
    assert 'choices=("mock", "nvidia")' in cli
