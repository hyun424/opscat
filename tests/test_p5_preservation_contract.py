"""Regression gates that preserve closed P5 behavior during P6 work."""

from __future__ import annotations

import re
from pathlib import Path

P5_TICKETS = tuple(f"P5-{number:03d}" for number in range(1, 19))


def test_p5_release_contract_stays_closed_and_local_mock() -> None:
    release_evidence = Path("docs/release-evidence.md").read_text()
    integration_evidence = Path("docs/integration-verification.md").read_text()
    p5_roadmap = Path("docs/operations/p5-ticket-roadmap.md").read_text()

    for ticket in P5_TICKETS:
        assert ticket in release_evidence
        assert f"### {ticket} ✅" in p5_roadmap

    for required in [
        "P5 final release evidence",
        "bash scripts/verify.sh --profile full",
        "Verification complete (full)",
        "auth remains deferred",
        "local/mock",
    ]:
        assert required in release_evidence

    for required in [
        "P5 final verification",
        "Result: PASS",
        "auth remains deferred",
        "local/mock",
        "does not claim real customer production readiness",
    ]:
        assert required in integration_evidence


def test_oss_quickstart_remains_credential_free_and_local_only() -> None:
    readme = Path("README.md").read_text()
    env_example = Path(".env.example").read_text()
    makefile = Path("Makefile").read_text()

    quickstart_target = re.search(r"^quickstart:\s*(?P<deps>[^\n]+)\n\t(?P<body>[^\n]+)", makefile, flags=re.MULTILINE)
    assert quickstart_target is not None
    assert quickstart_target.group("deps").split() == ["demo", "evals"]
    assert "No auth setup or production credentials" in quickstart_target.group("body")

    for required in [
        "make quickstart",
        "No auth setup is required",
        "auth is deferred",
        "local-header demo identity",
        "Do not use production credentials",
    ]:
        assert required in readme

    assert "OPSCAT_MODE=local-mock" in env_example
    assert "DATABASE_URL=sqlite:///./opscat.db" in env_example
    forbidden_markers = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY")
    assert all(marker not in env_example for marker in forbidden_markers)


def test_p6_plan_explicitly_preserves_p5_quickstart_boundaries() -> None:
    p6_roadmap = Path("docs/operations/p6-ticket-roadmap.md").read_text()

    for required in [
        "Keep OpsCat local-first/open-source usable",
        "existing local-header/demo identity boundary",
        "Fixture mode works without credentials and remains the default in quickstart/demo.",
        "auth remains deferred",
        "P6 does **not** include",
        "production customer credential collection",
        "unapproved production mutations",
    ]:
        assert required in p6_roadmap
