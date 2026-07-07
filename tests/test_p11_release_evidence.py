from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "secrets.")


def test_p11_final_summary_maps_tickets_to_artifacts() -> None:
    text = Path("docs/operations/p11-final-summary.md").read_text()
    for required in [
        "# OpsCat P11 Final Summary — Incident Corpus Expansion",
        "P11-001",
        "P11-002",
        "P11-003",
        "P11-004",
        "P11-005",
        "P11-006",
        "P11-007",
        "P11-008",
        "P11-009",
        "app/services/judgment_corpus.py",
        "scripts/run_corpus_audit.py",
        "evals/judgment/corpus/p11-corpus.json",
        "bash scripts/verify.sh --profile full",
        "no-auth/local-mock",
        "does not claim unattended production operation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p11_release_evidence_and_verify_include_corpus_audit() -> None:
    release = Path("docs/release-evidence.md").read_text()
    roadmap = Path("ROADMAP.md").read_text()
    verify = Path("scripts/verify.sh").read_text()
    for required in [
        "P11 Incident Corpus Expansion Evidence",
        "docs/operations/p11-ticket-roadmap.md",
        "docs/operations/p11-final-summary.md",
        "tests/test_judgment_corpus.py",
        "tests/test_judgment_corpus_cli.py",
        "tests/test_p11_release_evidence.py",
        "scripts/run_corpus_audit.py",
        "evals/judgment/corpus/p11-corpus.json",
        "/tmp/opscat-corpus-audit-latest.md",
        "bash scripts/verify.sh --profile full",
    ]:
        assert required in release
    assert "P11 implemented as local/mock Incident Corpus Expansion evidence" in roadmap
    assert "corpus_audit" in verify
