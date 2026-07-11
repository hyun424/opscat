from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import Any

import pytest

EXECUTOR_PATH = Path("app/services/prevention_canary_executor.py")
REQUIRED_ORDER = [
    "p106_recompute",
    "cohort_fingerprints",
    "policy_preflight",
    "idempotency_wal_intent",
    "harness_effect",
    "result_append",
    "monitoring",
    "report_handoff",
]


def _api() -> Any:
    try:
        return importlib.import_module("app.services.prevention_canary_executor")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P107 RED: missing prevention canary executor module ({exc}).", pytrace=False)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


class SpyStep:
    def __init__(self, name: str, calls: list[str], *, should_pass: bool = True) -> None:
        self.name = name
        self.calls = calls
        self.should_pass = should_pass

    def __call__(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append(self.name)
        if not self.should_pass:
            return {"passed": False, "status": "blocked_fail_closed", "failed_step": self.name}
        return {"passed": True, "status": "ok", "step": self.name, "hash": f"sha256:{self.name}"}


class HarnessSpy:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.effect_count = 0

    def __call__(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("harness_effect")
        self.effect_count += 1
        return {"passed": True, "status": "applied", "attempt_id": "attempt-1"}


def _executor(api: Any, calls: list[str], *, failing_step: str | None = None, harness: HarnessSpy | None = None) -> Any:
    cls = getattr(api, "PreventionCanaryExecutor", None)
    if cls is None:
        pytest.fail("P107 RED: expose PreventionCanaryExecutor.", pytrace=False)
    return cls(
        p106_recompute=SpyStep("p106_recompute", calls, should_pass=failing_step != "p106_recompute"),
        cohort_validator=SpyStep("cohort_fingerprints", calls, should_pass=failing_step != "cohort_fingerprints"),
        policy_preflight=SpyStep("policy_preflight", calls, should_pass=failing_step != "policy_preflight"),
        idempotency_wal=SpyStep("idempotency_wal_intent", calls, should_pass=failing_step != "idempotency_wal_intent"),
        harness=harness or HarnessSpy(calls),
        result_appender=SpyStep("result_append", calls, should_pass=True),
        monitor=SpyStep("monitoring", calls, should_pass=True),
        report_handoff=SpyStep("report_handoff", calls, should_pass=True),
    )


def _run(executor: Any) -> Any:
    run = getattr(executor, "run", None)
    if run is None:
        pytest.fail("P107 RED: PreventionCanaryExecutor must expose run(command).", pytrace=False)
    return run(
        {
            "episode_id": "p107-executor-contract",
            "candidate_hash": "sha256:candidate",
            "registry_hash": "sha256:registry",
            "cohort_hash": "sha256:cohort",
            "idempotency_key": "p107-executor-contract-key",
            "action": {"action_type": "mock.create_local_report"},
        }
    )


def _attr_chain(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _attr_chain(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Call):
        return _attr_chain(node.func)
    return ""


def test_executor_orchestrates_helpers_in_required_order() -> None:
    calls: list[str] = []
    harness = HarnessSpy(calls)
    result = _run(_executor(_api(), calls, harness=harness))

    assert calls == REQUIRED_ORDER
    assert harness.effect_count == 1
    assert _get(result, "terminal_state") in {"succeeded", "rolled_back", "escalated"}


@pytest.mark.parametrize("failing_step", ["p106_recompute", "cohort_fingerprints", "policy_preflight", "idempotency_wal_intent"])
def test_executor_never_attempts_before_helper_gates_pass(failing_step: str) -> None:
    calls: list[str] = []
    harness = HarnessSpy(calls)
    result = _run(_executor(_api(), calls, failing_step=failing_step, harness=harness))

    assert harness.effect_count == 0
    assert _get(result, "terminal_state") == "blocked_fail_closed"
    assert "harness_effect" not in calls


def test_unconfigured_executor_fails_closed_before_any_effect() -> None:
    cls = _api().PreventionCanaryExecutor

    result = _run(cls())

    assert _get(result, "terminal_state") == "blocked_fail_closed"
    assert _get(result, "effect_applied") is False
    assert _get(result, "success_claimed") is False
    assert _get(result, "failed_step") == "p106_recompute"


def test_executor_is_thin_orchestrator_not_helper_owner() -> None:
    api = _api()
    cls = getattr(api, "PreventionCanaryExecutor", None)
    if cls is None:
        pytest.fail("P107 RED: expose PreventionCanaryExecutor.", pytrace=False)

    expected_constructor_hooks = {
        "p106_recompute",
        "cohort_validator",
        "policy_preflight",
        "idempotency_wal",
        "harness",
        "result_appender",
        "monitor",
        "report_handoff",
    }
    init_varnames = set(cls.__init__.__code__.co_varnames)

    assert expected_constructor_hooks <= init_varnames


def test_executor_preserves_incident_execution_separation() -> None:
    assert EXECUTOR_PATH.exists(), "P107 RED: missing prevention_canary_executor.py for incident separation scan."
    tree = ast.parse(EXECUTOR_PATH.read_text(encoding="utf-8"), filename=str(EXECUTOR_PATH))

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported = {alias.name for alias in node.names}
            assert "ActionExecutionAttempt" not in imported
            assert node.module not in {"app.services.action_service", "app.services.execution_attempt_service"}
        if isinstance(node, ast.Import):
            imported_modules = {alias.name for alias in node.names}
            assert "app.services.action_service" not in imported_modules
            assert "app.services.execution_attempt_service" not in imported_modules
        if isinstance(node, (ast.Name, ast.Attribute, ast.Call)):
            chain = _attr_chain(node.func if isinstance(node, ast.Call) else node)
            assert chain != "ActionService.execute"
            assert chain != "ActionExecutionAttempt"
