from __future__ import annotations

from pathlib import Path


def test_p6_security_review_documents_agentic_boundaries_and_gaps() -> None:
    text = Path("docs/security-review-p6.md").read_text()

    for required in [
        "correlated evidence",
        "root-cause candidates",
        "runbooks",
        "policy decisions",
        "decision traces",
        "Auth/OIDC/SSO/session login remains explicitly deferred",
        "production mutation",
        "Cross-workspace merge",
    ]:
        assert required in text
    assert "not production-ready" in text
