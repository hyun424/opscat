"""P6 safety/threat-model documentation gates."""

from __future__ import annotations

from pathlib import Path


def test_p6_security_review_lists_assets_boundaries_threats_mitigations_and_gaps() -> None:
    text = Path("docs/security-review-p6.md").read_text()

    for required in [
        "# OpsCat P6 Safety and Threat Model Refresh",
        "## Assets",
        "## Trust boundaries",
        "## Abuse cases",
        "## Mitigations",
        "## Remaining gaps",
        "prompt/log injection",
        "malicious alert payloads",
        "secret exfiltration via evidence",
        "unsafe auto-remediation",
        "cross-workspace merge",
        "replay attacks",
        "eval overfitting",
        "auth remains deferred",
    ]:
        assert required in text
    assert "not production-ready" in text.lower()
    assert "unattended production mutation" not in text.lower()


def test_security_policy_links_p6_review_and_keeps_auth_deferred() -> None:
    text = Path("SECURITY.md").read_text()

    assert "docs/security-review-p6.md" in text
    assert "auth is deferred" in text
    assert "production credentials" in text
