from __future__ import annotations

import importlib
from typing import Any

import pytest


def _api() -> Any:
    try:
        return importlib.import_module("app.services.prevention_canary_executor")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P107 RED: missing prevention canary executor module ({exc}).", pytrace=False)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


class RollbackSpy:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.calls: list[str] = []

    def rollback(self, attempt: Any) -> dict[str, Any]:
        self.calls.append(_get(attempt, "attempt_id", "attempt-unknown"))
        if self.should_fail:
            return {"status": "failed", "terminal_state": "rollback_failed_escalated"}
        return {"status": "rolled_back", "terminal_state": "rolled_back"}


def _pass_step(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {"passed": True, "status": "ok", "hash": "sha256:explicit-test-gate"}


def _executor(api: Any, rollback: RollbackSpy | None = None) -> Any:
    cls = getattr(api, "PreventionCanaryExecutor", None)
    if cls is None:
        pytest.fail("P107 RED: expose PreventionCanaryExecutor.", pytrace=False)
    return cls(
        p106_recompute=_pass_step,
        cohort_validator=_pass_step,
        policy_preflight=_pass_step,
        idempotency_wal=_pass_step,
        result_appender=_pass_step,
        monitor=_pass_step,
        report_handoff=_pass_step,
        rollback_handler=rollback or RollbackSpy(),
    )


def _run(executor: Any, *, outcome: dict[str, Any]) -> Any:
    run = getattr(executor, "run", None)
    if run is None:
        pytest.fail("P107 RED: PreventionCanaryExecutor must expose run(command).", pytrace=False)
    return run(_safe_command(outcome))


def _safe_command(outcome: dict[str, Any]) -> dict[str, Any]:
    return {
        "episode_id": "p107-rollback-episode",
        "candidate_hash": "sha256:candidate",
        "registry_hash": "sha256:registry",
        "cohort_hash": "sha256:cohort",
        "idempotency_key": f"p107-rollback-{outcome['case_id']}",
        "action": {"action_type": "mock.create_rollback_artifact"},
        "post_attempt_outcome": outcome,
    }


@pytest.mark.parametrize(
    "outcome",
    [
        {"case_id": "guardrail_breach", "guardrail_status": "breached", "primary_metric_delta": -0.05, "telemetry_available": True},
        {"case_id": "non_improvement", "guardrail_status": "ok", "primary_metric_delta": 0.0, "telemetry_available": True},
        {"case_id": "uncertain", "guardrail_status": "uncertain", "primary_metric_delta": None, "telemetry_available": True},
        {"case_id": "telemetry_loss", "guardrail_status": "unknown", "primary_metric_delta": None, "telemetry_available": False},
    ],
)
def test_unsafe_or_inconclusive_outcome_rolls_back_or_escalates(outcome: dict[str, Any]) -> None:
    rollback = RollbackSpy()
    result = _run(_executor(_api(), rollback), outcome=outcome)

    assert _get(result, "success_claimed") is False
    assert _get(result, "terminal_state") in {"rolled_back", "rollback_failed_escalated", "escalated"}
    assert _get(result, "breach_without_rollback_or_escalation_count", 0) == 0


def test_rollback_failure_escalates_and_blocks_repeat() -> None:
    rollback = RollbackSpy(should_fail=True)
    executor = _executor(_api(), rollback)
    outcome = {"case_id": "rollback_failure", "guardrail_status": "breached", "primary_metric_delta": -1.0, "telemetry_available": True}

    first = _run(executor, outcome=outcome)
    second = _run(executor, outcome=outcome)

    assert _get(first, "terminal_state") == "rollback_failed_escalated"
    assert _get(first, "repeat_allowed") is False
    assert _get(second, "effect_applied") is False
    assert _get(second, "repeat_after_rollback_execution_count") == 0


def test_no_repeat_after_successful_rollback() -> None:
    rollback = RollbackSpy()
    executor = _executor(_api(), rollback)
    outcome = {"case_id": "successful_rollback", "guardrail_status": "breached", "primary_metric_delta": -1.0, "telemetry_available": True}

    first = _run(executor, outcome=outcome)
    second = _run(executor, outcome=outcome)

    assert _get(first, "terminal_state") == "rolled_back"
    assert _get(second, "effect_applied") is False
    assert _get(second, "repeat_after_rollback_execution_count") == 0
