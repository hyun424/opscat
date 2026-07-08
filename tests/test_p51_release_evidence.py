from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p51_docs_and_verify_are_wired() -> None:
    summary = Path("docs/operations/p51-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    fixture = Path("evals/investigator/p51_operator_judgment_benchmark_v2_cases.json").read_text(encoding="utf-8")
    for required in [
        "P51-001",
        "P51-002",
        "P51-003",
        "P51-004",
        "P51-005",
        "P51-006",
        "P51-007",
        "P51-008",
        "app/services/operator_judgment_benchmark_v2.py",
        "scripts/run_operator_judgment_benchmark_v2.py",
    ]:
        assert required in summary
    for required in ["P51 Operator Judgment Benchmark v2 Evidence", "tests/test_operator_judgment_benchmark_v2.py", "/tmp/opscat-operator-judgment-benchmark-v2-latest.md"]:
        assert required in release
    assert "operator_judgment_benchmark_v2_smoke" in verify
    assert "p51-deploy-anchoring-corrected" in fixture
    assert all(marker not in summary + release + fixture for marker in SECRET_MARKERS)
