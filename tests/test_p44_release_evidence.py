from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p44_ticket_manifest_documents_matrix_scope() -> None:
    roadmap = Path("docs/operations/p44-ticket-roadmap.md").read_text(encoding="utf-8")
    manifest = Path("evals/real_datasets/external/p44_benchmark_matrix_manifest.json").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P44 Ticket Roadmap — Larger Public Dataset Benchmark Matrix",
        "P44-001",
        "P44-002",
        "P44-003",
        "P44-004",
        "P44-005",
        "P44-006",
        "P44-007",
        "P44-008",
        "multi-source",
        "no live API calls",
    ]:
        assert required in roadmap
    for required in ["loghub-apache-2k", "loghub-linux-2k", "nab-machine-temperature", "nab-ambient-temperature", "nab-ec2-cpu"]:
        assert required in manifest
    assert all(marker not in roadmap + manifest for marker in SECRET_MARKERS)


def test_p44_release_evidence_summary_and_verify_exist() -> None:
    summary = Path("docs/operations/p44-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P44 Final Summary — Larger Public Dataset Benchmark Matrix",
        "P44-001",
        "P44-002",
        "P44-003",
        "P44-004",
        "P44-005",
        "P44-006",
        "P44-007",
        "P44-008",
        "app/services/public_dataset_matrix.py",
        "scripts/run_public_dataset_matrix.py",
        "source-level",
        "family-level",
        "no unattended production-operation claim",
    ]:
        assert required in summary
    for required in [
        "P44 Larger Public Dataset Benchmark Matrix Evidence",
        "docs/operations/p44-ticket-roadmap.md",
        "docs/operations/p44-final-summary.md",
        "tests/test_public_dataset_matrix.py",
        "tests/test_p44_release_evidence.py",
        "/tmp/opscat-public-dataset-matrix-latest.md",
    ]:
        assert required in release
    assert "P44 active scope: Larger Public Dataset Benchmark Matrix" in roadmap
    assert "public_dataset_matrix_smoke" in verify
    assert all(marker not in summary + release for marker in SECRET_MARKERS)
