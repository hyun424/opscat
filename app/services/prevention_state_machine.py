"""P107 prevention episode state machine.

This module is deliberately data-only: it defines the transition contract used
by audit replay and small in-process validators.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
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

TERMINAL_STATES: set[str] = {
    "blocked_fail_closed",
    "succeeded",
    "rolled_back",
    "rollback_failed_escalated",
    "escalated",
    "replay_invalid",
}

ALL_STATES: set[str] = set(ALLOWED_TRANSITIONS) | TERMINAL_STATES


class PreventionStateTransitionError(ValueError):
    """Raised when an episode state append violates the P107 table."""


@dataclass
class PreventionStateMachine:
    """Append-only validator for P107 state progress."""

    states: list[str] = field(default_factory=list)

    @property
    def current_state(self) -> str | None:
        return self.states[-1] if self.states else None

    def append(self, state: str) -> None:
        state = str(state)
        if state not in ALL_STATES:
            raise PreventionStateTransitionError(f"unknown prevention state {state!r}")

        current = self.current_state
        if current in TERMINAL_STATES:
            raise PreventionStateTransitionError(f"cannot append {state!r} after terminal state {current!r}")
        if state in TERMINAL_STATES and any(existing in TERMINAL_STATES for existing in self.states):
            raise PreventionStateTransitionError(f"terminal state {state!r} would create a second terminal")

        if current is None:
            if state != "received":
                raise PreventionStateTransitionError(f"incomplete episode: first state must be 'received', got {state!r}")
        elif state not in ALLOWED_TRANSITIONS.get(current, set()):
            raise PreventionStateTransitionError(f"invalid transition from {current!r} to {state!r}")

        self.states.append(state)

    @property
    def terminal(self) -> bool:
        return self.current_state in TERMINAL_STATES
