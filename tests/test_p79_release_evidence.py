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
    "Authorization",
    "Bearer",
)


def test_p79_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p79-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p79-final-summary.md").read_text(encoding="utf-8")
    roadmap_index = Path("ROADMAP.md").read_text(encoding="utf-8")

    for required in ["P79-001", "P79-002", "P79-003", "P79-004", "P79-005", "P79-006", "P79-007", "P79-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P79 Action Sandbox Hardening Evidence",
        "app/services/action_sandbox_hardening.py",
        "scripts/run_action_sandbox_hardening.py",
        "tests/test_action_sandbox_hardening.py",
        "evals/actions/p79_action_sandbox_cases.json",
        "/tmp/opscat-action-sandbox-hardening-latest.md",
    ]:
        assert required in release
    assert "action_sandbox_hardening_smoke" in verify
    assert "P79 active scope: Action Sandbox Hardening" in roadmap_index
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
