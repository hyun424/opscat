from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p43_ticket_manifest_documents_public_benchmark_scope() -> None:
    roadmap = Path("docs/operations/p43-ticket-roadmap.md").read_text(encoding="utf-8")
    manifest = Path("evals/real_datasets/external/p43_public_benchmark_manifest.json").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P43 Ticket Roadmap — Opt-in Public Dataset Download & Benchmark Scorecard",
        "P43-001",
        "P43-002",
        "P43-003",
        "P43-004",
        "P43-005",
        "P43-006",
        "P43-007",
        "P43-008",
        "explicit opt-in",
        "no live API calls",
    ]:
        assert required in roadmap
    for required in ["loghub-apache-2k", "nab-machine-temperature", "data_url", "labels_url", "local_fixture"]:
        assert required in manifest
    assert all(marker not in roadmap + manifest for marker in SECRET_MARKERS)


def test_p43_release_evidence_summary_and_verify_exist() -> None:
    summary = Path("docs/operations/p43-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P43 Final Summary — Opt-in Public Dataset Download & Benchmark Scorecard",
        "P43-001",
        "P43-002",
        "P43-003",
        "P43-004",
        "P43-005",
        "P43-006",
        "P43-007",
        "P43-008",
        "app/services/public_dataset_benchmark.py",
        "scripts/run_public_dataset_benchmark.py",
        "public download benchmark",
        "no unattended production-operation claim",
    ]:
        assert required in summary
    for required in [
        "P43 Opt-in Public Dataset Download & Benchmark Scorecard Evidence",
        "docs/operations/p43-ticket-roadmap.md",
        "docs/operations/p43-final-summary.md",
        "tests/test_public_dataset_benchmark.py",
        "tests/test_p43_release_evidence.py",
        "/tmp/opscat-public-dataset-benchmark-latest.md",
    ]:
        assert required in release
    assert "P43 active scope: Opt-in Public Dataset Download & Benchmark Scorecard" in roadmap
    assert "public_dataset_benchmark_smoke" in verify
    assert all(marker not in summary + release for marker in SECRET_MARKERS)
