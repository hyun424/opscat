from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p46_docs_and_verify_are_wired() -> None:
    summary = Path("docs/operations/p46-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    fixture = Path("evals/investigator/p46_investigation_cases.json").read_text(encoding="utf-8")
    for required in ["P46-001", "P46-002", "P46-003", "P46-004", "P46-005", "P46-006", "P46-007", "P46-008", "app/services/investigator_loop.py", "scripts/run_investigator_loop.py"]:
        assert required in summary
    for required in ["P46 Investigator Loop Evidence", "tests/test_investigator_loop.py", "/tmp/opscat-investigator-loop-latest.md"]:
        assert required in release
    assert "investigator_loop_smoke" in verify
    assert "p46-payment-5xx" in fixture
    assert all(marker not in summary + release + fixture for marker in SECRET_MARKERS)
