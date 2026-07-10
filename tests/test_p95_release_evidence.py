from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = (
    "sk_live_",
    "xoxb-",
    "ghp_",
    "sntrys_",
    "BEGIN PRIVATE KEY",
    "prod-token",
    "nvapi-",
    "actual-secret-value",
    "Authorization",
    "Bearer",
)


def test_p95_clean_clone_evidence_is_recorded() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p95-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p95-final-summary.md").read_text(encoding="utf-8")
    roadmap_index = Path("ROADMAP.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in ["P95-001", "P95-002", "P95-003", "P95-004", "P95-005", "P95-006"]:
        assert required in roadmap
        assert required in summary

    assert "P95 Clean-Clone Reproducibility Gate" in release
    assert "P95 Final Summary — Clean-Clone Reproducibility Gate" in summary

    for required in [
        "https://github.com/hyun424/opscat",
        "c5a187d7ef2b13e9ada0b336b8bdf6d38ed700e3",
        "cp .env.example .env",
        "make install",
        "make quickstart",
        "bash scripts/verify.sh --profile full",
        "80.71% >= 60.00%",
        "OPSCAT_MODE=local-mock",
        "LocalEncryptedSecretProvider",
        "No auth setup or production credentials were required",
        ".env",
        ".DS_Store",
        ".venv",
        "opscat.db",
    ]:
        assert required in release
        assert required in summary

    assert "P95 active scope: Clean-Clone Reproducibility Gate" in roadmap_index
    assert "P95 implemented as Clean-Clone Reproducibility evidence" in roadmap_index
    assert "tests/test_p95_release_evidence.py" in verify
    assert "Clean-clone reproducibility" in readme
    assert "make quickstart" in readme
    assert all(marker not in release + roadmap + summary + readme for marker in SECRET_MARKERS)
