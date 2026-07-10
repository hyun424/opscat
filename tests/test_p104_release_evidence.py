from pathlib import Path


def _read(path: str) -> str:
    file_path = Path(path)
    assert file_path.exists(), f"{path} must exist for P104 release integration"
    return file_path.read_text(encoding="utf-8")


def test_p104_release_evidence_documents_evidence_gap_investigator_results() -> None:
    roadmap = _read("docs/operations/p104-ticket-roadmap.md")
    review = _read("docs/operations/p104-plan-review.md")
    summary = _read("docs/operations/p104-final-summary.md")
    release = _read("docs/release-evidence.md")
    project_roadmap = _read("ROADMAP.md")
    changelog = _read("CHANGELOG.md")
    readme = _read("README.md")

    for ticket_number in range(0, 11):
        assert f"P104-{ticket_number:03d}" in roadmap
    for marker in (
        "Evidence Gap Investigator",
        "scripts/run_evidence_gap_investigator.py",
        "app/services/evidence_gap_investigator.py",
        "evals/evidence_gap/seed/scenarios.json",
        "tests/test_evidence_gap_investigator.py",
        "tests/test_p104_release_evidence.py",
        "does not prove production",
    ):
        assert marker.lower() in summary.lower()
    assert "## P104 Evidence Gap Investigator" in release
    assert "## P104 implemented" in project_roadmap
    assert "P104 evidence gap" in changelog
    assert "scripts/run_evidence_gap_investigator.py" in readme
    assert "network-free" in readme.lower()
    assert "advisory" in readme.lower()
    assert "cannot declare sufficiency" in review


def test_p104_release_evidence_wires_verification_profile_and_smoke_command() -> None:
    verify = _read("scripts/verify.sh")

    assert "evidence_gap_investigator_smoke" in verify
    assert "P104 evidence-gap investigator smoke" in verify
    assert "scripts/run_evidence_gap_investigator.py" in verify
    assert "tests/test_evidence_gap_investigator.py" in verify
    assert "tests/test_p104_release_evidence.py" in verify
    assert "opscat-p104-evidence-gap-investigator.json" in verify
    assert "opscat-p104-evidence-gap-investigator.md" in verify
    assert "--include-nvidia" not in verify.partition("evidence_gap_investigator_smoke")[2].partition("}")[0]
    assert "--network-enabled" not in verify.partition("evidence_gap_investigator_smoke")[2].partition("}")[0]


def test_p104_release_evidence_states_offline_boundaries_and_grounded_safety_claims() -> None:
    summary = _read("docs/operations/p104-final-summary.md")
    release = _read("docs/release-evidence.md")
    rendered = "\n".join((summary, release)).lower()

    for marker in (
        "no auth",
        "no production mutation",
        "no mutating diagnostics",
        "default network calls: 0",
        "default model calls: 0",
        "action_authority=false",
        "provider action execution count: 0",
        "production mutation count: 0",
        "scorer leakage count: 0",
        "repeated tool count: 0",
        "false-remediation handoff rate",
        "p103",
        "valid absence",
        "unavailable",
    ):
        assert marker in rendered

    assert "benchmark evidence" in rendered
    assert "safety counters" in rendered
    assert "not production" in rendered


def test_p104_cli_artifacts_exist_and_default_contract_is_offline_action_disabled() -> None:
    cli = _read("scripts/run_evidence_gap_investigator.py")
    service = _read("app/services/evidence_gap_investigator.py")
    seed = _read("evals/evidence_gap/seed/scenarios.json")

    assert "run_evidence_gap_cli" in cli
    assert "build_evidence_gap_cli_parser" in cli
    assert "--include-nvidia" in service
    assert "--network-enabled" in service
    assert '"default_network_calls": 0' in service
    assert '"provider_model_call_count"' in service
    assert '"action_authority": False' in service
    assert '"production_mutation_enabled": False' in service
    assert '"read_only_tools_only": True' in service
    assert "p104.evidence_gap.seed.v1" in seed


def test_p104_evidence_contains_no_secret_material() -> None:
    paths = (
        "docs/operations/p104-ticket-roadmap.md",
        "docs/operations/p104-plan-review.md",
        "docs/operations/p104-final-summary.md",
        "docs/release-evidence.md",
        "README.md",
        "CHANGELOG.md",
    )
    rendered = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in paths
        if Path(path).exists()
    )
    for marker in ("nvapi-", "sk_live_", "xoxb-", "ghp_", "BEGIN PRIVATE KEY"):
        assert marker not in rendered
