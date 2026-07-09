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


def test_p92_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p92-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p92-final-summary.md").read_text(encoding="utf-8")
    roadmap_index = Path("ROADMAP.md").read_text(encoding="utf-8")

    for required in ["P92-001", "P92-002", "P92-003", "P92-004", "P92-005", "P92-006", "P92-007", "P92-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P92 Operator Replacement Acceptance Drill v3 / Product Quality Evidence Pack",
        "app/services/operator_replacement_acceptance_drill_v3.py",
        "scripts/run_operator_replacement_acceptance_drill_v3.py",
        "tests/test_operator_replacement_acceptance_drill_v3.py",
        "evals/actions/p92_operator_replacement_acceptance_drill_v3.json",
        "/tmp/opscat-operator-replacement-acceptance-drill-v3-latest.md",
    ]:
        assert required in release
    assert "operator_replacement_acceptance_drill_v3_smoke" in verify
    assert "P92 active scope: Operator Replacement Acceptance Drill v3 / Product Quality Evidence Pack" in roadmap_index
    assert "P92 implemented as Operator Replacement Acceptance Drill v3 evidence" in roadmap_index
    assert "local/mock demo ready" in release
    assert "forbidden claims" in release
    assert "not production autonomy" in release
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
