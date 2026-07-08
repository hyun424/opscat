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


def test_p77_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p77-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p77-final-summary.md").read_text(encoding="utf-8")
    for required in ["P77-001", "P77-002", "P77-003", "P77-004", "P77-005", "P77-006", "P77-007", "P77-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P77 Recovery Proof Engine Evidence",
        "app/services/recovery_proof_engine.py",
        "scripts/run_recovery_proof_engine.py",
        "tests/test_recovery_proof_engine.py",
        "/tmp/opscat-recovery-proof-engine-latest.md",
    ]:
        assert required in release
    assert "recovery_proof_engine_smoke" in verify
    assert "P77 active scope: Recovery Proof Engine" in Path("ROADMAP.md").read_text(encoding="utf-8")
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
