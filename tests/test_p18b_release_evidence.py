from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-")


def test_p18b_ticket_roadmap_lists_model_quality_lab_scope() -> None:
    text = Path("docs/operations/p18b-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P18B Ticket Roadmap — Model Judgment Quality Lab",
        "P18B-001",
        "P18B-002",
        "P18B-003",
        "P18B-004",
        "P18B-005",
        "P18B-006",
        "P18B-007",
        "P18B-008",
        "No auth work",
        "No production mutation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p18b_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p18b-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P18B Final Summary — Model Judgment Quality Lab",
        "P18B-001",
        "P18B-002",
        "P18B-003",
        "P18B-004",
        "P18B-005",
        "P18B-006",
        "P18B-007",
        "P18B-008",
        "app/services/model_quality_lab.py",
        "scripts/run_model_quality_eval.py",
        "tests/test_model_quality_lab.py",
        "raw_provider_score",
        "calibrated_score",
        "failure taxonomy",
        "no-auth/local-mock by default",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P18B Model Judgment Quality Lab Evidence",
        "docs/operations/p18b-ticket-roadmap.md",
        "docs/operations/p18b-final-summary.md",
        "tests/test_model_quality_lab.py",
        "tests/test_p18b_release_evidence.py",
        "/tmp/opscat-model-quality-latest.md",
    ]:
        assert required in release
    assert "P18B implemented as Model Judgment Quality Lab evidence" in roadmap
    assert "model_quality_lab_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
