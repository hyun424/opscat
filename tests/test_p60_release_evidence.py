from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p60_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p60-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p60-final-summary.md").read_text(encoding="utf-8")
    for required in ["P60-001", "P60-002", "P60-003", "P60-004", "P60-005", "P60-006", "P60-007"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P60 Operator Replacement Readiness Gate v2 Evidence",
        "app/services/operator_replacement_readiness_gate_v2.py",
        "scripts/run_operator_replacement_readiness_gate_v2.py",
        "tests/test_operator_replacement_readiness_gate_v2.py",
        "/tmp/opscat-operator-replacement-readiness-gate-v2-latest.md",
    ]:
        assert required in release
    assert "operator_replacement_readiness_gate_v2_smoke" in verify
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
