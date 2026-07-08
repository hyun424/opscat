from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p41_ticket_roadmap_lists_raw_dataset_scope() -> None:
    text = Path("docs/operations/p41-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P41 Ticket Roadmap — Raw Real Dataset Scored Replay",
        "P41-001",
        "P41-002",
        "P41-003",
        "P41-004",
        "P41-005",
        "P41-006",
        "P41-007",
        "P41-008",
        "repo-local raw dataset files only",
        "no external dataset downloads during verification",
        "no live API calls",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p41_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p41-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P41 Final Summary — Raw Real Dataset Scored Replay",
        "P41-001",
        "P41-002",
        "P41-003",
        "P41-004",
        "P41-005",
        "P41-006",
        "P41-007",
        "P41-008",
        "app/services/raw_real_dataset_replay.py",
        "scripts/run_raw_real_dataset_replay.py",
        "evals/real_datasets/raw/p41_sources.json",
        "root-cause accuracy",
        "no unattended production-operation claim",
    ]:
        assert required in summary
    for required in [
        "P41 Raw Real Dataset Scored Replay Evidence",
        "docs/operations/p41-ticket-roadmap.md",
        "docs/operations/p41-final-summary.md",
        "tests/test_raw_real_dataset_replay.py",
        "tests/test_p41_release_evidence.py",
        "/tmp/opscat-raw-real-dataset-replay-latest.md",
    ]:
        assert required in release
    assert "P41 active scope: Raw Real Dataset Scored Replay" in roadmap
    assert "raw_real_dataset_replay_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
