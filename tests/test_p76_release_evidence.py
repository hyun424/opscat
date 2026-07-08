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


def test_p76_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p76-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p76-final-summary.md").read_text(encoding="utf-8")
    for required in ["P76-001", "P76-002", "P76-003", "P76-004", "P76-005", "P76-006", "P76-007", "P76-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P76 Evidence Sufficiency Gate v2 Evidence",
        "app/services/evidence_sufficiency_gate_v2.py",
        "scripts/run_evidence_sufficiency_gate_v2.py",
        "tests/test_evidence_sufficiency_gate_v2.py",
        "/tmp/opscat-evidence-sufficiency-gate-v2-latest.md",
    ]:
        assert required in release
    assert "evidence_sufficiency_gate_v2_smoke" in verify
    assert "P76 active scope: Evidence Sufficiency Gate v2" in Path("ROADMAP.md").read_text(encoding="utf-8")
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
