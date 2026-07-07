from __future__ import annotations

from pathlib import Path


SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "secrets.")


def test_p7_security_review_documents_assets_threats_and_boundaries() -> None:
    path = Path("docs/security-review-p7.md")

    assert path.exists()
    text = path.read_text()
    for required in [
        "# OpsCat P7 Security Review",
        "local/mock",
        "Auth/OIDC/SSO/session login remains explicitly deferred",
        "replay poisoning",
        "adversarial log injection",
        "overconfident diagnosis",
        "memory poisoning",
        "Night Autopilot v2",
        "does not claim unattended production operation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p7_final_summary_records_review_lane_and_verification_plan() -> None:
    path = Path("docs/operations/p7-final-summary.md")

    assert path.exists()
    text = path.read_text()
    for required in [
        "# OpsCat P7 Final Summary — Agent Reliability & Safety Lab",
        "P7 Review and Documentation Handoff",
        "five coordinated lanes",
        "docs/operations/p7-ticket-roadmap.md",
        "docs/operations/p7-code-quality-review.md",
        "no-auth/local-mock",
        "Verification plan",
        "bash scripts/verify.sh --profile full",
        "does not claim unattended production operation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p7_release_evidence_and_roadmap_expose_reviewer_commands() -> None:
    release = Path("docs/release-evidence.md").read_text()
    roadmap = Path("ROADMAP.md").read_text()

    for required in [
        "P7 Agent Reliability & Safety Lab Evidence",
        "docs/operations/p7-ticket-roadmap.md",
        "docs/operations/p7-final-summary.md",
        "docs/security-review-p7.md",
        "scripts/run_replay_evals.py",
        "/tmp/opscat-replay-evals-latest.md",
        "does not claim unattended production operation",
    ]:
        assert required in release

    assert "P7 active scope: Agent Reliability & Safety Lab without auth" in roadmap
    assert "no-auth/local-mock" in roadmap
    assert all(marker not in release for marker in SECRET_MARKERS)
