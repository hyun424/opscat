from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "secrets.")


def test_p10_final_summary_maps_tickets_to_artifacts() -> None:
    text = Path("docs/operations/p10-final-summary.md").read_text()
    for required in [
        "# OpsCat P10 Final Summary — Incident Judgment Benchmark",
        "P10-001",
        "P10-002",
        "P10-003",
        "P10-004",
        "P10-005",
        "P10-006",
        "P10-007",
        "P10-008",
        "P10-009",
        "P10-010",
        "P10-011",
        "P10-012",
        "scripts/run_judgment_benchmark.py",
        "scripts/import_judgment_dataset.py",
        "bash scripts/verify.sh --profile full",
        "no-auth/local-mock",
        "does not claim unattended production operation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p10_release_evidence_and_verify_include_benchmark() -> None:
    release = Path("docs/release-evidence.md").read_text()
    roadmap = Path("ROADMAP.md").read_text()
    verify = Path("scripts/verify.sh").read_text()
    for required in [
        "P10 Incident Judgment Benchmark Evidence",
        "docs/operations/p10-ticket-roadmap.md",
        "docs/operations/p10-final-summary.md",
        "tests/test_judgment_dataset.py",
        "tests/test_judgment_benchmark.py",
        "scripts/run_judgment_benchmark.py",
        "/tmp/opscat-judgment-benchmark-latest.md",
        "bash scripts/verify.sh --profile full",
    ]:
        assert required in release
    assert "P10 implemented as local/mock Incident Judgment Benchmark evidence" in roadmap
    assert "judgment_benchmark" in verify
