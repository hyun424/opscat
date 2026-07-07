from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "secrets.")


def test_p12_final_summary_maps_tickets_to_artifacts() -> None:
    text = Path("docs/operations/p12-final-summary.md").read_text()
    for required in [
        "# OpsCat P12 Final Summary — Real Dataset Evaluation Harness",
        "P12-001",
        "P12-002",
        "P12-003",
        "P12-004",
        "P12-005",
        "P12-006",
        "P12-007",
        "P12-008",
        "P12-009",
        "P12-010",
        "P12-011",
        "P12-012",
        "app/services/real_dataset_evaluation.py",
        "scripts/import_real_dataset.py",
        "scripts/run_real_dataset_eval.py",
        "evals/real_datasets/fixtures/manifest.json",
        "bash scripts/verify.sh --profile full",
        "no-auth/local-mock",
        "does not claim unattended production operation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p12_release_evidence_and_verify_include_real_dataset_eval() -> None:
    release = Path("docs/release-evidence.md").read_text()
    roadmap = Path("ROADMAP.md").read_text()
    verify = Path("scripts/verify.sh").read_text()
    for required in [
        "P12 Real Dataset Evaluation Harness Evidence",
        "docs/operations/p12-ticket-roadmap.md",
        "docs/operations/p12-final-summary.md",
        "tests/test_real_dataset_evaluation.py",
        "tests/test_real_dataset_cli.py",
        "tests/test_p12_release_evidence.py",
        "scripts/import_real_dataset.py",
        "scripts/run_real_dataset_eval.py",
        "evals/real_datasets/fixtures/manifest.json",
        "/tmp/opscat-real-dataset-eval-latest.md",
        "bash scripts/verify.sh --profile full",
    ]:
        assert required in release
    assert "P12 implemented as local/mock Real Dataset Evaluation Harness evidence" in roadmap
    assert "real_dataset_eval" in verify
