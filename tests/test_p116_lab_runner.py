from __future__ import annotations

from app.services.causal_remediation_benchmark import build_causal_scenario_catalog
from app.services.p110_evaluation import stable_hash
from app.services.p116_lab_runner import P116_LAB_BOUNDARY, P116PairedLabRunner
from app.services.p116_paired_outcomes import P116_REQUIRED_ARMS, build_p116_paired_outcome_record, hash_p116_source_results


def test_lab_runner_produces_deterministic_isolated_five_arm_records() -> None:
    scenario = next(case for case in build_causal_scenario_catalog() if case.family == "deploy_config" and case.variant == "obvious")
    runner = P116PairedLabRunner(sample_size=5)

    first = runner.run(cases=[scenario], seeds=[11, 13]).to_dict()
    second = runner.run(cases=[scenario], seeds=[11, 13]).to_dict()

    assert first["run_hash"] == second["run_hash"]
    assert len(first["arm_results"]) == 10
    for seed in (11, 13):
        paired = [result for result in first["arm_results"] if result["seed"] == seed]
        assert {result["arm"] for result in paired} == set(P116_REQUIRED_ARMS)
        assert len({result["initial_fingerprint"] for result in paired}) == 1
        assert {result["reset_receipt"]["arm_order"] for result in paired} == set(range(5))
        for result in paired:
            receipt = result["reset_receipt"]
            assert receipt["verified"] is True
            assert receipt["receipt_hash"] == stable_hash({key: value for key, value in receipt.items() if key != "receipt_hash"})


def test_lab_output_is_directly_consumable_by_paired_outcome_contract() -> None:
    scenario = next(case for case in build_causal_scenario_catalog() if case.family == "database" and case.variant == "obvious")
    run = P116PairedLabRunner(sample_size=5).run(cases=[scenario], seeds=[17]).to_dict()
    arms = run["arm_results"]

    record = build_p116_paired_outcome_record(
        arms,
        boundary=P116_LAB_BOUNDARY,
        expected_source_hash=hash_p116_source_results(arms),
    ).to_dict()

    assert record["case_id"] == scenario.case_id
    assert record["reset_verification"]["required_arms_present"] is True
    assert record["authority"]["production_mutation_enabled"] is False
    assert record["causal_attribution"]["wrong_action_harm_observed"] is True


def test_selected_arm_uses_measured_validation_before_evidence_bound_followup() -> None:
    scenario = next(
        case
        for case in build_causal_scenario_catalog()
        if case.family == "deploy_config" and case.variant == "partial_recovery"
    )
    run = P116PairedLabRunner(sample_size=20).run(cases=[scenario], seeds=[23]).to_dict()
    selected = next(result for result in run["arm_results"] if result["arm"] == "selected_action")

    assert selected["decision"]["actions"] == ["rollback_deploy", "restart_service"]
    assert selected["post"]["recovered"] is True
    assert selected["durability"]["recovered"] is True
    assert selected["post"]["collateral_regressions"] == 0
