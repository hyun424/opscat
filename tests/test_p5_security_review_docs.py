"""P5 security/threat-model review documentation contract."""

from __future__ import annotations

from pathlib import Path

SURFACES = [
    "connector setup",
    "secret lifecycle",
    "incident import",
    "worker CLI",
    "approval console",
    "Night Autopilot",
    "self-observability",
]


def test_p5_security_review_lists_surfaces_adversarial_checks_and_gaps() -> None:
    path = Path("docs/security-review-p5.md")

    assert path.exists()
    text = path.read_text()
    for required in [
        "# P5 Security Review",
        "Adversarial checks",
        "Residual gaps",
        "auth remains deferred",
        "no production credentials",
        "fail closed",
        "redaction",
        "tenant/workspace scope",
    ]:
        assert required in text
    for surface in SURFACES:
        assert surface in text


def test_threat_model_links_p5_security_review() -> None:
    text = Path("docs/threat-model.md").read_text()

    assert "docs/security-review-p5.md" in text
    assert "Residual gaps" in text
    for surface in SURFACES:
        assert surface in text
