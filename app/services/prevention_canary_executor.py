"""Thin P107 canary prevention executor orchestrator."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from app.services.prevention_canary_harness import REGISTERED_LOCAL_MOCK_HANDLERS, PreventionCanaryHarness
from app.services.prevention_guardrail_rollback import PreventionGuardrailRollback, repeat_lock_key

Step = Callable[..., Mapping[str, Any]]


@dataclass
class PreventionCanaryExecutor:
    p106_recompute: Step | None = None
    cohort_validator: Step | None = None
    policy_preflight: Step | None = None
    idempotency_wal: Step | None = None
    harness: Any | None = None
    result_appender: Step | None = None
    monitor: Step | None = None
    report_handoff: Step | None = None
    rollback_handler: Any | None = None

    def __post_init__(self) -> None:
        self.p106_recompute = self.p106_recompute or _missing_step("p106_recompute")
        self.cohort_validator = self.cohort_validator or _missing_step("cohort_fingerprints")
        self.policy_preflight = self.policy_preflight or _missing_step("policy_preflight")
        self.idempotency_wal = self.idempotency_wal or _missing_step("idempotency_wal_intent")
        self.harness = self.harness or PreventionCanaryHarness()
        self.result_appender = self.result_appender or _missing_step("result_append")
        self.monitor = self.monitor or _missing_step("monitoring")
        self.report_handoff = self.report_handoff or _missing_step("report_handoff")
        self._rollback = PreventionGuardrailRollback(self.rollback_handler)

    def run(self, command: Mapping[str, Any]) -> dict[str, Any]:
        command_map = dict(command)
        repeat_attempt = _attempt_from_command(command_map, {"attempt_id": "repeat-probe"})
        if repeat_lock_key(repeat_attempt) in self._rollback._blocked_repeat_keys:
            return _finalize(
                {
                    "terminal_state": "blocked_fail_closed",
                    "effect_applied": False,
                    "success_claimed": False,
                    "repeat_allowed": False,
                    "repeat_after_rollback_execution_count": 0,
                    "breach_without_rollback_or_escalation_count": 0,
                }
            )

        for step_name, hook in (
            ("p106_recompute", self.p106_recompute),
            ("cohort_fingerprints", self.cohort_validator),
            ("policy_preflight", self.policy_preflight),
            ("idempotency_wal_intent", self.idempotency_wal),
        ):
            result = _call_hook(hook, command_map)
            if not _passed(result):
                return _blocked(step_name, result)

        harness_result = self._run_harness(command_map)
        if not _passed(harness_result):
            return _finalize(harness_result, terminal_state="blocked_fail_closed", effect_applied=False)

        result_append = _call_hook(self.result_appender, command_map, harness_result)
        if not _passed(result_append):
            return _blocked("result_append", result_append)

        monitor_result = _call_hook(self.monitor, command_map, harness_result)
        if not _passed(monitor_result):
            return _blocked("monitoring", monitor_result)

        outcome = _outcome(command_map)
        if outcome is None:
            terminal = str(monitor_result.get("terminal_state", harness_result.get("terminal_state", "succeeded")))
            body = {"terminal_state": terminal, "success_claimed": terminal == "succeeded", "effect_applied": True}
        else:
            attempt = _attempt_from_command(command_map, harness_result)
            body = self._rollback.assess(attempt, outcome)

        report_result = _call_hook(self.report_handoff, command_map, body)
        body.setdefault("report_handoff", dict(report_result))
        return _finalize(body)

    def _run_harness(self, command: Mapping[str, Any]) -> Mapping[str, Any]:
        action = dict(_mapping(command.get("action")))
        action.setdefault("idempotency_key", command.get("idempotency_key"))
        if "action_type" not in action:
            action["action_type"] = "mock.create_local_report"
        action.setdefault(
            "capability_id",
            command.get("capability_id", REGISTERED_LOCAL_MOCK_HANDLERS.get(str(action["action_type"]), "preventive.mock.report")),
        )

        if callable(self.harness):
            return _mapping(self.harness(command))
        execute = getattr(self.harness, "execute", None)
        if callable(execute):
            return _mapping(execute(action))
        invoke = getattr(self.harness, "invoke", None)
        if callable(invoke):
            return _mapping(invoke(dict(command)))
        return {"passed": False, "status": "blocked_fail_closed", "reason": "harness_unavailable"}


def _missing_step(name: str) -> Step:
    def _step(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "passed": False,
            "status": "blocked_fail_closed",
            "step": name,
            "reason": f"required hook {name} is not configured",
        }

    return _step


def _call_hook(hook: Any, *args: Any) -> Mapping[str, Any]:
    if not callable(hook):
        return {"passed": False, "status": "blocked_fail_closed", "reason": "hook_unavailable"}
    return _mapping(hook(*args))


def _passed(result: Mapping[str, Any]) -> bool:
    if result.get("passed") is False or result.get("accepted") is False:
        return False
    status = str(result.get("status", "ok"))
    terminal = str(result.get("terminal_state", ""))
    return status != "blocked_fail_closed" and terminal != "blocked_fail_closed"


def _blocked(step_name: str, result: Mapping[str, Any]) -> dict[str, Any]:
    return _finalize(
        {
            "terminal_state": "blocked_fail_closed",
            "failed_step": step_name,
            "gate_result": dict(result),
            "success_claimed": False,
            "effect_applied": False,
        }
    )


def _finalize(result: Mapping[str, Any], *, terminal_state: str | None = None, effect_applied: bool | None = None) -> dict[str, Any]:
    body = dict(result)
    body["terminal_state"] = terminal_state or str(body.get("terminal_state", "succeeded"))
    if effect_applied is not None:
        body["effect_applied"] = effect_applied
    body.setdefault("success_claimed", body["terminal_state"] == "succeeded")
    body.setdefault("repeat_after_rollback_execution_count", 0)
    body.setdefault("breach_without_rollback_or_escalation_count", 0)
    return body


def _attempt_from_command(command: Mapping[str, Any], harness_result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": harness_result.get("attempt_id", "attempt-unknown"),
        "episode_id": command.get("episode_id", ""),
        "capability_id": command.get("capability_id", _mapping(command.get("action")).get("capability_id", "")),
        "cohort_hash": command.get("cohort_hash", command.get("cohort_fingerprint_hash", "")),
        "idempotency_key": command.get("idempotency_key", ""),
    }


def _outcome(command: Mapping[str, Any]) -> Mapping[str, Any] | None:
    value = command.get("post_attempt_outcome")
    return value if isinstance(value, Mapping) else None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
