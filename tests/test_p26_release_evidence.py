from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-")


def test_p26_ticket_roadmap_lists_adapter_scope() -> None:
    text = Path("docs/operations/p26-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P26 Ticket Roadmap — Real Telemetry Adapter Contract",
        "P26-001",
        "P26-002",
        "P26-003",
        "P26-004",
        "P26-005",
        "P26-006",
        "P26-007",
        "P26-008",
        "no live API calls",
        "no remediation execution",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p26_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p26-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P26 Final Summary — Real Telemetry Adapter Contract",
        "P26-001",
        "P26-002",
        "P26-003",
        "P26-004",
        "P26-005",
        "P26-006",
        "P26-007",
        "P26-008",
        "app/services/telemetry_adapter.py",
        "scripts/run_telemetry_adapter.py",
        "evals/telemetry/fixtures/prometheus_query_range.json",
        "Prometheus",
        "Datadog",
        "Sentry",
        "no-auth/local-mock by default",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P26 Real Telemetry Adapter Contract Evidence",
        "docs/operations/p26-ticket-roadmap.md",
        "docs/operations/p26-final-summary.md",
        "tests/test_telemetry_adapter_contract.py",
        "tests/test_p26_release_evidence.py",
        "/tmp/opscat-telemetry-adapter-latest.md",
    ]:
        assert required in release
    assert "P26 implemented as Real Telemetry Adapter Contract evidence" in roadmap
    assert "telemetry_adapter_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
