from __future__ import annotations

from app.services.p110_evaluation import stable_hash
from app.services.p115_scenario_matrix import build_p115_scenario_matrix
from app.services.p117_benchmark import run_p117_deterministic_tournament


def test_frozen_benchmark_runs_600_identically_denominated_episodes() -> None:
    release = _p116_release()

    run = run_p117_deterministic_tournament(p116_release_evidence=release)

    assert len(run["episode_manifest"]["episodes"]) == 600
    report = run["tournament_report"]
    deterministic = report["selectors"]["deterministic"]["metrics"]
    assert report["identical_denominators"] is True
    assert deterministic["accuracy"]["value"] == 1.0
    assert deterministic["contract_validity"]["value"] == 1.0
    assert deterministic["authority_violation_count"] == 0
    assert deterministic["measured_utility"]["value"] > report["selectors"]["safe_null"]["metrics"]["measured_utility"]["value"]
    assert report["report_hash"] == run["replay_report"]["report_hash"]


def _p116_release() -> dict[str, object]:
    matrix = build_p115_scenario_matrix()
    labels = {str(item["case_id"]): str(item["evaluator_label"]) for item in matrix.evaluator_labels}
    records = []
    for case in matrix.cases:
        case_id = str(case["case_id"])
        utility = 0.4 if labels[case_id] in {"action", "harmful_or_ineffective"} else 0.0
        record = {
            "case_id": case_id,
            "record_hash": stable_hash({"record": case_id}),
            "source_hash": stable_hash({"source": case_id}),
            "measurement_status": "comparable",
            "slo_deltas": {"selected_action": {"utility_delta": utility}},
        }
        records.append(record)
    payload: dict[str, object] = {"paired_outcome_records": records}
    payload["release_evidence_hash"] = stable_hash(payload)
    return payload
