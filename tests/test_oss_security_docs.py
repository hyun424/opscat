"""OSS security and safe disclosure documentation contracts."""

from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token")
PRODUCTION_READY_CLAIMS = (
    "production-ready authentication",
    "SOC2 compliant",
    "safe for real customer production use today",
)


def test_security_policy_states_public_scope_and_safe_disclosure() -> None:
    path = Path("SECURITY.md")

    assert path.exists()
    text = path.read_text()
    for required in [
        "# Security Policy",
        "local/mock",
        "Do not submit secrets",
        "Do not submit customer logs",
        "auth is deferred",
        "safe disclosure",
        "production credentials",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_threat_model_covers_p5_oss_surfaces_without_auth_claims() -> None:
    path = Path("docs/threat-model.md")

    assert path.exists()
    text = path.read_text()
    for required in [
        "connector setup",
        "secret lifecycle",
        "incident import",
        "worker CLI",
        "approval console",
        "self-observability",
        "auth remains deferred",
    ]:
        assert required in text
    assert all(claim not in text for claim in PRODUCTION_READY_CLAIMS)


def test_contributor_docs_include_action_connector_safety_checklist() -> None:
    text = Path("CONTRIBUTING.md").read_text()

    for required in [
        "Safety checklist",
        "No production credentials",
        "fixture-backed or dry-run",
        "redaction",
        "approval-gated",
        "connector eval",
        "Do not include secrets",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)
