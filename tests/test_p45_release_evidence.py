from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p45_docs_and_fixture_exist() -> None:
    roadmap = Path("docs/operations/p45-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p45-final-summary.md").read_text(encoding="utf-8")
    fixture = Path("evals/investigator/p45_judgment_cases.json").read_text(encoding="utf-8")
    for required in ["P45-001", "P45-002", "P45-003", "P45-004", "P45-005", "P45-006", "P45-007", "P45-008", "supporting evidence", "counter-evidence"]:
        assert required in roadmap
    for required in ["app/services/evidence_grounded_judgment.py", "scripts/run_evidence_grounded_judgment.py", "confidence", "action boundaries"]:
        assert required in summary
    for required in ["p45-deploy-regression", "p45-db-saturation", "p45-ambiguous"]:
        assert required in fixture
    assert all(marker not in roadmap + summary + fixture for marker in SECRET_MARKERS)


def test_p45_release_evidence_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    for required in ["P45 Evidence-Grounded Judgment Contract Evidence", "tests/test_evidence_grounded_judgment.py", "tests/test_p45_release_evidence.py", "/tmp/opscat-evidence-grounded-judgment-latest.md"]:
        assert required in release
    assert "P45 active scope: Evidence-Grounded Judgment Contract" in roadmap
    assert "evidence_grounded_judgment_smoke" in verify
    assert all(marker not in release for marker in SECRET_MARKERS)
