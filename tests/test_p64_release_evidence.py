from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = (
    "sk_live_",
    "xoxb-",
    "ghp_",
    "sntrys_",
    "BEGIN PRIVATE KEY",
    "prod-token",
    "nvapi-",
    "actual-secret-value",
    "mock-grafana-read-token",
    "mock-sentry-read-token",
    "mock-datadog-read-token",
    "Authorization",
    "Bearer",
)


def test_p64_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p64-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p64-final-summary.md").read_text(encoding="utf-8")
    for required in ["P64-001", "P64-002", "P64-003", "P64-004", "P64-005", "P64-006", "P64-007", "P64-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P64 Audited Staging Credential + Transport Gate Evidence",
        "evals/staging/p64_audited_credential_transport_gate.json",
        "app/services/audited_staging_transport_gate.py",
        "scripts/run_audited_staging_transport_gate.py",
        "tests/test_audited_staging_transport_gate.py",
        "/tmp/opscat-audited-staging-transport-gate-latest.md",
    ]:
        assert required in release
    assert "audited_staging_transport_gate_smoke" in verify
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
