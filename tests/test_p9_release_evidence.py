from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "secrets.")


def test_p9_final_summary_maps_all_tickets_to_artifacts_and_verification() -> None:
    text = Path("docs/operations/p9-final-summary.md").read_text()
    for required in [
        "# OpsCat P9 Final Summary — Autonomous Incident Commander",
        "P9-001",
        "P9-002",
        "P9-003",
        "P9-004",
        "P9-005",
        "P9-006",
        "P9-007",
        "P9-008",
        "P9-009",
        "P9-010",
        "app/services/incident_commander.py",
        "app/services/response_planner.py",
        "app/services/autonomy_readiness.py",
        "app/services/evidence_graph.py",
        "app/services/recovery_verifier.py",
        "app/services/commander_learning.py",
        "scripts/run_commander_tournament.py",
        "tests/test_p9_commander_safety.py",
        "bash scripts/verify.sh --profile full",
        "no-auth/local-mock",
        "does not claim unattended production operation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p9_release_evidence_roadmap_and_verify_profile_expose_commander_gate() -> None:
    release = Path("docs/release-evidence.md").read_text()
    roadmap = Path("ROADMAP.md").read_text()
    verify = Path("scripts/verify.sh").read_text()

    for required in [
        "P9 Autonomous Incident Commander Evidence",
        "docs/operations/p9-ticket-roadmap.md",
        "docs/operations/p9-final-summary.md",
        "docs/security-review-p9.md",
        "tests/test_incident_commander.py",
        "tests/test_p9_commander_tournament.py",
        "tests/test_p9_commander_safety.py",
        "tests/test_p9_commander_ui.py",
        "scripts/run_commander_tournament.py",
        "/tmp/opscat-p9-commander-tournament-latest.json",
        "bash scripts/verify.sh --profile full",
        "does not claim unattended production operation",
    ]:
        assert required in release
    assert "P9 implemented as local/mock Autonomous Incident Commander evidence" in roadmap
    assert "commander_tournament" in verify
    assert all(marker not in release for marker in SECRET_MARKERS)
