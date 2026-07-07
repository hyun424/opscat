from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "secrets.")


def test_p8_security_review_documents_new_threats_and_auth_deferral() -> None:
    path = Path("docs/security-review-p8.md")

    assert path.exists()
    text = path.read_text()
    for required in [
        "# OpsCat P8 Security Review",
        "local/mock",
        "Auth/OIDC/SSO/session login remains explicitly deferred",
        "stale or poisoned incident memory",
        "over-trusting reliability score",
        "prompt/log injection in war room text",
        "secret exposure in evidence or report export",
        "unsafe runbook improvement suggestions",
        "UI implying production autonomy",
        "does not claim unattended production operation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p8_threat_model_addendum_maps_mitigations_to_tests() -> None:
    text = Path("docs/threat-model.md").read_text()

    for required in [
        "P8 AI Incident Responder War Room Addendum",
        "war room",
        "agent reliability score",
        "runbook critique",
        "human question generation",
        "report export",
        "tests/test_p8_demo.py",
        "tests/test_p8_security_docs.py",
        "auth remains deferred",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)
