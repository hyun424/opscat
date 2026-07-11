from __future__ import annotations

import importlib
from typing import Any

import pytest

EXPECTED_ALLOWED_TRANSITIONS = {
    "received": {"p106_recomputed"},
    "p106_recomputed": {"cohort_checked", "blocked_fail_closed"},
    "cohort_checked": {"policy_rechecked", "blocked_fail_closed"},
    "policy_rechecked": {"wal_intent_appended", "blocked_fail_closed"},
    "wal_intent_appended": {"attempt_effect_observed", "blocked_fail_closed"},
    "attempt_effect_observed": {"result_appended"},
    "result_appended": {"monitoring"},
    "monitoring": {"succeeded", "rollback_intent_appended", "escalated", "blocked_fail_closed"},
    "rollback_intent_appended": {"rollback_effect_observed"},
    "rollback_effect_observed": {"rollback_result_appended"},
    "rollback_result_appended": {"rolled_back", "rollback_failed_escalated"},
}

EXPECTED_TERMINAL_STATES = {
    "blocked_fail_closed",
    "succeeded",
    "rolled_back",
    "rollback_failed_escalated",
    "escalated",
    "replay_invalid",
}


def _api() -> Any:
    try:
        return importlib.import_module("app.services.prevention_state_machine")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P107 RED: missing prevention state machine implementation ({exc}).", pytrace=False)


def _normalized_transition_table(api: Any) -> dict[str, set[str]]:
    table = getattr(api, "ALLOWED_TRANSITIONS", None)
    if table is None:
        pytest.fail("P107 RED: expose ALLOWED_TRANSITIONS for machine-checked audit replay.", pytrace=False)
    return {str(source): {str(target) for target in targets} for source, targets in dict(table).items()}


def _terminal_states(api: Any) -> set[str]:
    terminal_states = getattr(api, "TERMINAL_STATES", None)
    if terminal_states is None:
        pytest.fail("P107 RED: expose TERMINAL_STATES for terminal exclusivity checks.", pytrace=False)
    return {str(state) for state in terminal_states}


def _new_machine(api: Any) -> Any:
    machine_cls = getattr(api, "PreventionStateMachine", None)
    if machine_cls is None:
        pytest.fail("P107 RED: expose PreventionStateMachine.append(state) for audit replay.", pytrace=False)
    return machine_cls()


def _append(machine: Any, state: str) -> None:
    try:
        machine.append(state)
    except Exception as exc:  # noqa: BLE001 - tests assert contract-level rejection messages below.
        raise AssertionError(f"unexpected rejection while appending {state!r}: {exc}") from exc


def _assert_rejected(machine: Any, state: str, expected_reason: str) -> None:
    with pytest.raises(Exception) as raised:
        machine.append(state)
    assert expected_reason in str(raised.value).lower()


def test_state_transition_table_is_complete_and_machine_checked() -> None:
    api = _api()

    assert _normalized_transition_table(api) == EXPECTED_ALLOWED_TRANSITIONS
    assert _terminal_states(api) == EXPECTED_TERMINAL_STATES


@pytest.mark.parametrize("first_terminal", sorted(EXPECTED_TERMINAL_STATES - {"replay_invalid"}))
def test_terminal_states_are_exclusive(first_terminal: str) -> None:
    api = _api()
    machine = _new_machine(api)
    sequence_by_terminal = {
        "blocked_fail_closed": ["received", "p106_recomputed", "blocked_fail_closed"],
        "succeeded": [
            "received",
            "p106_recomputed",
            "cohort_checked",
            "policy_rechecked",
            "wal_intent_appended",
            "attempt_effect_observed",
            "result_appended",
            "monitoring",
            "succeeded",
        ],
        "rolled_back": [
            "received",
            "p106_recomputed",
            "cohort_checked",
            "policy_rechecked",
            "wal_intent_appended",
            "attempt_effect_observed",
            "result_appended",
            "monitoring",
            "rollback_intent_appended",
            "rollback_effect_observed",
            "rollback_result_appended",
            "rolled_back",
        ],
        "rollback_failed_escalated": [
            "received",
            "p106_recomputed",
            "cohort_checked",
            "policy_rechecked",
            "wal_intent_appended",
            "attempt_effect_observed",
            "result_appended",
            "monitoring",
            "rollback_intent_appended",
            "rollback_effect_observed",
            "rollback_result_appended",
            "rollback_failed_escalated",
        ],
        "escalated": [
            "received",
            "p106_recomputed",
            "cohort_checked",
            "policy_rechecked",
            "wal_intent_appended",
            "attempt_effect_observed",
            "result_appended",
            "monitoring",
            "escalated",
        ],
    }
    for state in sequence_by_terminal[first_terminal]:
        _append(machine, state)

    _assert_rejected(machine, "blocked_fail_closed", "terminal")


def test_attempt_before_policy_recheck_is_rejected() -> None:
    machine = _new_machine(_api())
    for state in ["received", "p106_recomputed", "cohort_checked"]:
        _append(machine, state)

    _assert_rejected(machine, "wal_intent_appended", "transition")


@pytest.mark.parametrize("terminal_state", sorted(EXPECTED_TERMINAL_STATES - {"replay_invalid"}))
def test_append_after_terminal_is_rejected(terminal_state: str) -> None:
    machine = _new_machine(_api())
    sequences = {
        "blocked_fail_closed": ["received", "p106_recomputed", "blocked_fail_closed"],
        "succeeded": [
            "received",
            "p106_recomputed",
            "cohort_checked",
            "policy_rechecked",
            "wal_intent_appended",
            "attempt_effect_observed",
            "result_appended",
            "monitoring",
            "succeeded",
        ],
        "rolled_back": [
            "received",
            "p106_recomputed",
            "cohort_checked",
            "policy_rechecked",
            "wal_intent_appended",
            "attempt_effect_observed",
            "result_appended",
            "monitoring",
            "rollback_intent_appended",
            "rollback_effect_observed",
            "rollback_result_appended",
            "rolled_back",
        ],
        "rollback_failed_escalated": [
            "received",
            "p106_recomputed",
            "cohort_checked",
            "policy_rechecked",
            "wal_intent_appended",
            "attempt_effect_observed",
            "result_appended",
            "monitoring",
            "rollback_intent_appended",
            "rollback_effect_observed",
            "rollback_result_appended",
            "rollback_failed_escalated",
        ],
        "escalated": [
            "received",
            "p106_recomputed",
            "cohort_checked",
            "policy_rechecked",
            "wal_intent_appended",
            "attempt_effect_observed",
            "result_appended",
            "monitoring",
            "escalated",
        ],
    }
    for state in sequences[terminal_state]:
        _append(machine, state)

    _assert_rejected(machine, "monitoring", "terminal")


def test_rollback_states_require_attempt_effect() -> None:
    machine = _new_machine(_api())
    for state in ["received", "p106_recomputed", "cohort_checked", "policy_rechecked"]:
        _append(machine, state)

    _assert_rejected(machine, "rollback_intent_appended", "transition")
