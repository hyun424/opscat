from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p50_docs_and_verify_are_wired() -> None:
    summary = Path("docs/operations/p50-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    fixture = Path("evals/investigator/p50_night_operator_cases.json").read_text(encoding="utf-8")
    for required in [
        "P50-001",
        "P50-002",
        "P50-003",
        "P50-004",
        "P50-005",
        "P50-006",
        "P50-007",
        "P50-008",
        "app/services/night_operator_drill_v2.py",
        "scripts/run_night_operator_drill_v2.py",
    ]:
        assert required in summary
    for required in ["P50 Night Operator Drill v2 Evidence", "tests/test_night_operator_drill_v2.py", "/tmp/opscat-night-operator-drill-v2-latest.md"]:
        assert required in release
    assert "night_operator_drill_v2_smoke" in verify
    assert "p50-night-db-saturation" in fixture
    assert all(marker not in summary + release + fixture for marker in SECRET_MARKERS)
