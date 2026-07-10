from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from tests.fixtures.p106_p105_release_archive import safe_extract_p105_release_archive


def _api() -> Any:
    try:
        return importlib.import_module("app.services.preventive_action_benchmark")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P106 RED: missing P106 release evidence producer surface ({exc}).", pytrace=False)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def test_release_evidence_requires_zero_authority_and_no_llm_authority() -> None:
    api = _api()
    producer = getattr(api, "produce_p106_release_evidence", None)
    if producer is None:
        pytest.fail("P106 RED: expose produce_p106_release_evidence(...).", pytrace=False)

    evidence = producer(cases_path=Path("evals/prevention/p106_benchmark_cases.json"))

    assert _get(evidence, "authority") == {
        "auth_enabled": False,
        "production_mutation_enabled": False,
        "action_authority": False,
        "remediation_execution_enabled": False,
        "default_external_model_calls": 0,
    }
    assert _get(evidence, "llm_can_override_policy") is False
    assert _get(evidence, "llm_can_unlock_p107") is False
    assert _get(evidence, "production_mutation_enabled") is False


def test_release_evidence_records_required_p106_metrics_and_stop_condition() -> None:
    producer = getattr(_api(), "produce_p106_release_evidence", None)
    if producer is None:
        pytest.fail("P106 RED: expose produce_p106_release_evidence(...).", pytrace=False)

    evidence = producer(cases_path=Path("evals/prevention/p106_benchmark_cases.json"))

    assert {"planner_regret", "harmful_action_rate", "policy_fail_closed_rate"} <= set(_get(evidence, "metrics", {}))
    assert _get(evidence, "harmful_action_rate") == 0.0
    assert _get(evidence, "shared_fail_closed_fixture_hash")
    assert _get(evidence, "p107_unlock_condition") == "shared_fail_closed_passed AND zero_harmful_actions AND mutation_plans_simulation_only"
    assert _get(evidence, "p107_unlocked") is False


def test_actual_hash_bound_benchmark_can_only_establish_p107_gate_eligibility(tmp_path: Path) -> None:
    api = _api()
    artifact = safe_extract_p105_release_archive(
        Path("evals/prevention/p105_release_qualified_real_derived.tar.gz"),
        tmp_path / "p105",
    )
    evidence = api.produce_p106_release_evidence(
        cases_path=Path("evals/prevention/p106_benchmark_cases.json"),
        p105_artifact_path=artifact,
    )
    gate = api.evaluate_p107_unlock_gate(evidence)

    assert gate["p107_gate_eligible"] is True
    assert gate["p107_unlocked"] is False
    assert evidence["benchmark_run_identity"]["sha256"].startswith("sha256:")


@pytest.mark.parametrize(
    ("field", "forged"),
    [
        ("planner_regret", 0.99),
        ("safe_fallback_rate", 0.0),
        ("policy_fail_closed_rate", 0.0),
        ("eligible_planner_evaluation_count", 999),
    ],
)
def test_p107_gate_rejects_tampered_top_level_benchmark_claims(
    tmp_path: Path,
    field: str,
    forged: float | int,
) -> None:
    api = _api()
    artifact = safe_extract_p105_release_archive(
        Path("evals/prevention/p105_release_qualified_real_derived.tar.gz"),
        tmp_path / "p105",
    )
    evidence = api.produce_p106_release_evidence(
        cases_path=Path("evals/prevention/p106_benchmark_cases.json"),
        p105_artifact_path=artifact,
    )
    evidence[field] = forged

    gate = api.evaluate_p107_unlock_gate(evidence)

    assert gate["p107_gate_eligible"] is False
    assert gate["operands"]["benchmark_run_identity_current"] is False


def test_p106_release_docs_do_not_claim_production_authority_if_docs_exist() -> None:
    docs = [
        Path("docs/operations/p106-ticket-roadmap.md"),
        Path("docs/operations/p106-final-summary.md"),
        Path("docs/release-evidence.md"),
        Path("README.md"),
        Path("CHANGELOG.md"),
    ]
    forbidden = ["production mutation enabled", "live remediation execution", "llm authority", "p107 unlocked by p106"]

    for path in docs:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").lower()
        for phrase in forbidden:
            assert phrase not in text, f"{path} overclaims P106 boundary: {phrase}"
