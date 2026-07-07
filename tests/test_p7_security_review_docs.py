from __future__ import annotations

from pathlib import Path


def test_p7_security_review_documents_assets_threats_and_auth_deferral() -> None:
    text = Path("docs/security-review-p7.md").read_text()
    for phrase in ("replay", "adversarial", "confidence calibration", "self-critique", "action simulation", "incident memory", "Night Autopilot v2", "auth remains deferred"):
        assert phrase in text
