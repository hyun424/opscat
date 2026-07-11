from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.services.prevention_canary_fixture_matrix import REQUIRED_METRIC_GATES

CANARY_CASES_PATH = Path("evals/prevention/p107_canary_cases.json")
CANARY_EVIDENCE_CLI = Path("scripts/run_prevention_canary_evidence.py")
REQUIRED_FIXTURE_IDS = tuple(f"A{index:02d}" for index in range(1, 15))
REQUIRED_EVIDENCE_GATES = {
    "p106_gate_recomputed",
    "cohort_fingerprints_equalized",
    "policy_preflight_passed",
    "local_mock_adapter_only",
    "primary_metric_window_met",
    "guardrail_window_met",
    "rollback_or_escalation_verified",
    "idempotency_replay_verified",
    "no_release_replay_as_recovery",
    "zero_authority_counters",
}


def _api() -> Any:
    try:
        return importlib.import_module("app.services.prevention_canary_fixture_matrix")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P107 RED: missing prevention canary fixture matrix module ({exc}).", pytrace=False)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _complete_matrix() -> dict[str, Any]:
    return {
        "schema_version": "p107.canary_fixture_matrix.v1",
        "fixtures": [
            {
                "fixture_id": fixture_id,
                "scenario": f"scenario-{fixture_id.lower()}",
                "expected_terminal_state": "succeeded" if fixture_id not in {"A03", "A06", "A11"} else "rolled_back",
                "evidence_gates": {gate: True for gate in REQUIRED_EVIDENCE_GATES},
                "recovery_replay_hash": f"sha256:recovery-{fixture_id.lower()}",
                "release_replay_hash": f"sha256:release-{fixture_id.lower()}",
                "authority_counters": {
                    "auth": 0,
                    "credential_reads": 0,
                    "production_adapter_calls": 0,
                    "production_mutation": 0,
                    "network_calls": 0,
                    "shell_calls": 0,
                    "cloud_calls": 0,
                    "db_mutation": 0,
                },
                "command": {"fixture_id": fixture_id, "adapter": "local_mock"},
            }
            for fixture_id in REQUIRED_FIXTURE_IDS
        ],
        "metric_gates": dict(REQUIRED_METRIC_GATES),
    }


def _evaluate(matrix: dict[str, Any]) -> Any:
    evaluator = getattr(_api(), "evaluate_prevention_canary_fixture_matrix", None)
    if evaluator is None:
        pytest.fail(
            "P107 RED: expose evaluate_prevention_canary_fixture_matrix(matrix).",
            pytrace=False,
        )
    return evaluator(matrix)


def test_fixture_matrix_requires_exact_a01_through_a14_coverage() -> None:
    result = _evaluate(_complete_matrix())

    assert _get(result, "accepted") is True
    assert tuple(_get(result, "fixture_ids")) == REQUIRED_FIXTURE_IDS
    assert _get(result, "missing_fixture_ids") == []


def test_fixture_matrix_rejects_missing_a01_a14_fixture() -> None:
    matrix = _complete_matrix()
    matrix["fixtures"] = [fixture for fixture in matrix["fixtures"] if fixture["fixture_id"] != "A14"]

    result = _evaluate(matrix)

    assert _get(result, "accepted") is False
    assert "A14" in _get(result, "missing_fixture_ids")


@pytest.mark.parametrize("gate", sorted(REQUIRED_EVIDENCE_GATES))
def test_each_fixture_requires_every_evidence_gate(gate: str) -> None:
    matrix = _complete_matrix()
    matrix["fixtures"][0]["evidence_gates"][gate] = False

    result = _evaluate(matrix)

    assert _get(result, "accepted") is False
    assert gate in _get(result, "failed_gates_by_fixture")["A01"]


def test_fixture_matrix_rejects_reused_recovery_and_release_replay_hash() -> None:
    matrix = _complete_matrix()
    matrix["fixtures"][1]["release_replay_hash"] = matrix["fixtures"][1]["recovery_replay_hash"]

    result = _evaluate(matrix)

    assert _get(result, "accepted") is False
    assert "A02" in _get(result, "replay_separation_failures")


def test_fixture_matrix_rejects_nonzero_authority_counter() -> None:
    matrix = _complete_matrix()
    matrix["fixtures"][2]["authority_counters"]["production_mutation"] = 1

    result = _evaluate(matrix)

    assert _get(result, "accepted") is False
    assert _get(result, "authority_counter_failures") == {"A03": {"production_mutation": 1}}


def test_fixture_matrix_fails_closed_without_metric_gates() -> None:
    matrix = _complete_matrix()
    matrix.pop("metric_gates")

    result = _evaluate(matrix)

    assert _get(result, "accepted") is False
    assert set(_get(result, "metric_gate_failures")) == set(REQUIRED_METRIC_GATES)


def test_fixture_matrix_fails_closed_without_command_contract() -> None:
    matrix = _complete_matrix()
    matrix["fixtures"][0].pop("command")

    result = _evaluate(matrix)

    assert _get(result, "accepted") is False
    assert _get(result, "command_failures")["A01"] == ["missing_command"]


def test_real_p107_canary_cases_fixture_file_matches_matrix_contract() -> None:
    assert CANARY_CASES_PATH.exists(), f"P107 RED: missing real canary fixture file {CANARY_CASES_PATH}"

    matrix = json.loads(CANARY_CASES_PATH.read_text(encoding="utf-8"))
    result = _evaluate(matrix)

    assert matrix["schema_version"] == "p107.canary_fixture_matrix.v1"
    assert tuple(fixture["fixture_id"] for fixture in matrix["fixtures"]) == REQUIRED_FIXTURE_IDS
    assert _get(result, "accepted") is True
    assert _get(result, "matrix_source_path") == str(CANARY_CASES_PATH)


def test_real_p107_canary_cases_include_required_cli_fields() -> None:
    assert CANARY_CASES_PATH.exists(), f"P107 RED: missing real canary fixture file {CANARY_CASES_PATH}"

    matrix = json.loads(CANARY_CASES_PATH.read_text(encoding="utf-8"))

    for fixture in matrix["fixtures"]:
        assert set(fixture["evidence_gates"]) == REQUIRED_EVIDENCE_GATES
        assert fixture["command"]["fixture_id"] == fixture["fixture_id"]
        assert fixture["command"]["adapter"] == "local_mock"
        assert fixture["expected_terminal_state"] in {"succeeded", "rolled_back", "escalated", "blocked_fail_closed"}
        assert fixture["recovery_replay_hash"].startswith("sha256:")
        assert fixture["release_replay_hash"].startswith("sha256:")


def test_canary_evidence_cli_uses_real_fixture_file_by_default() -> None:
    assert CANARY_EVIDENCE_CLI.exists(), f"P107 RED: missing canary evidence CLI {CANARY_EVIDENCE_CLI}"
    assert CANARY_CASES_PATH.exists(), f"P107 RED: missing real canary fixture file {CANARY_CASES_PATH}"

    result = subprocess.run(
        [sys.executable, str(CANARY_EVIDENCE_CLI), "--dry-run"],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["fixture_path"] == str(CANARY_CASES_PATH)
    assert tuple(payload["fixture_ids"]) == REQUIRED_FIXTURE_IDS
    assert payload["would_execute"] is True


def test_canary_evidence_cli_rejects_non_p107_fixture_path(tmp_path: Path) -> None:
    assert CANARY_EVIDENCE_CLI.exists(), f"P107 RED: missing canary evidence CLI {CANARY_EVIDENCE_CLI}"
    wrong_fixture = tmp_path / "cases.json"
    wrong_fixture.write_text(json.dumps(_complete_matrix()), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(CANARY_EVIDENCE_CLI), "--fixture-path", str(wrong_fixture), "--dry-run"],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "evals/prevention/p107_canary_cases.json" in result.stderr
