from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "Bearer secret-token")


def test_p29_ticket_roadmap_lists_telemetry_judgment_scope() -> None:
    text = Path("docs/operations/p29-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P29 Ticket Roadmap — Telemetry-grounded Judgment Quality Evaluation",
        "P29-001",
        "P29-002",
        "P29-003",
        "P29-004",
        "P29-005",
        "P29-006",
        "P29-007",
        "P29-008",
        "no default external model calls",
        "no remediation execution",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p29_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p29-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P29 Final Summary — Telemetry-grounded Judgment Quality Evaluation",
        "P29-001",
        "P29-002",
        "P29-003",
        "P29-004",
        "P29-005",
        "P29-006",
        "P29-007",
        "P29-008",
        "app/services/telemetry_judgment_quality.py",
        "scripts/run_telemetry_judgment_eval.py",
        "evals/judgment/telemetry_grounded/p29_cases.json",
        "telemetry-grounded judgment quality",
        "NVIDIA opt-in",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P29 Telemetry-grounded Judgment Quality Evaluation Evidence",
        "docs/operations/p29-ticket-roadmap.md",
        "docs/operations/p29-final-summary.md",
        "tests/test_telemetry_judgment_quality.py",
        "tests/test_p29_release_evidence.py",
        "/tmp/opscat-telemetry-judgment-quality-latest.md",
    ]:
        assert required in release
    assert "P29 implemented as Telemetry-grounded Judgment Quality Evaluation evidence" in roadmap
    assert "telemetry_judgment_quality_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
