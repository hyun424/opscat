from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p42_ticket_roadmap_and_manifest_document_scope() -> None:
    roadmap = Path("docs/operations/p42-ticket-roadmap.md").read_text(encoding="utf-8")
    manifest = Path("evals/real_datasets/external/p42_manifest.json").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P42 Ticket Roadmap — External Dataset Acquisition & Holdout Evaluation",
        "P42-001",
        "P42-002",
        "P42-003",
        "P42-004",
        "P42-005",
        "P42-006",
        "P42-007",
        "P42-008",
        "no external downloads",
        "no live API calls",
    ]:
        assert required in roadmap
    for required in ["loghub-apache", "nab-real-known-cause", "sample_url", "local_fixture", "dry_run"]:
        assert required in manifest
    assert all(marker not in roadmap + manifest for marker in SECRET_MARKERS)


def test_p42_release_evidence_summary_and_verify_exist() -> None:
    summary = Path("docs/operations/p42-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P42 Final Summary — External Dataset Acquisition & Holdout Evaluation",
        "P42-001",
        "P42-002",
        "P42-003",
        "P42-004",
        "P42-005",
        "P42-006",
        "P42-007",
        "P42-008",
        "app/services/external_dataset_acquisition.py",
        "scripts/prepare_external_datasets.py",
        "holdout",
        "no unattended production-operation claim",
    ]:
        assert required in summary
    for required in [
        "P42 External Dataset Acquisition & Holdout Evaluation Evidence",
        "docs/operations/p42-ticket-roadmap.md",
        "docs/operations/p42-final-summary.md",
        "tests/test_external_dataset_acquisition.py",
        "tests/test_p42_release_evidence.py",
        "/tmp/opscat-external-dataset-acquisition-latest.md",
    ]:
        assert required in release
    assert "P42 active scope: External Dataset Acquisition & Holdout Evaluation" in roadmap
    assert "external_dataset_acquisition_smoke" in verify
    assert all(marker not in summary + release for marker in SECRET_MARKERS)
