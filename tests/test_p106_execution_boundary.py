from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import Any

import pytest

P106_SOURCE_FILES = [
    Path("app/services/p105_release_prerequisite.py"),
    Path("app/services/preventive_capability_registry.py"),
    Path("app/services/preventive_action_planner.py"),
    Path("app/services/preventive_expected_value.py"),
    Path("app/services/preventive_safety_gate.py"),
    Path("app/services/prevention_planning_lab.py"),
    Path("app/services/preventive_action_llm_adapter.py"),
    Path("app/services/preventive_action_benchmark.py"),
    Path("scripts/run_preventive_action_benchmark.py"),
]
FORBIDDEN_NAMES = {"MockActionExecutor", "execute_mock_action", "start_action_attempt", "record_execution_result"}


def _attr_chain(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _attr_chain(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Call):
        return _attr_chain(node.func)
    return ""


def test_p106_modules_never_import_forbidden_execution_symbols() -> None:
    present = [path for path in P106_SOURCE_FILES if path.exists()]
    assert present, "P106 RED: no P106 modules exist yet; implementation must add simulation-only modules."

    for path in present:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported = {alias.name for alias in node.names}
                assert imported.isdisjoint(FORBIDDEN_NAMES), f"{path} imports forbidden execution symbol {imported & FORBIDDEN_NAMES}"
            if isinstance(node, ast.Import):
                assert all(alias.name != "app.services.action_executor" for alias in node.names)


def test_p106_modules_never_reference_or_call_execution_apis() -> None:
    present = [path for path in P106_SOURCE_FILES if path.exists()]
    assert present, "P106 RED: no P106 modules exist yet; implementation must add simulation-only modules."

    for path in present:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id not in FORBIDDEN_NAMES, f"{path} references forbidden symbol {node.id}"
            if isinstance(node, ast.Attribute):
                chain = _attr_chain(node)
                assert chain != "ActionService.execute"
                assert not any(chain.endswith(f".{name}") for name in FORBIDDEN_NAMES)
            if isinstance(node, ast.Call):
                chain = _attr_chain(node.func)
                assert chain != "ActionService.execute"
                assert not any(chain.endswith(f".{name}") for name in FORBIDDEN_NAMES)


def test_planner_never_touches_execution_runtime_on_any_route(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        planner_api = importlib.import_module("app.services.preventive_action_planner")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P106 RED: missing preventive action planner module ({exc}).", pytrace=False)

    touched: list[str] = []

    class SpyActionService:
        def execute(self, *_args: Any, **_kwargs: Any) -> None:
            touched.append("ActionService.execute")

    monkeypatch.setattr(planner_api, "ActionService", SpyActionService, raising=False)
    for name in FORBIDDEN_NAMES:
        monkeypatch.setattr(planner_api, name, lambda *_args, _name=name, **_kwargs: touched.append(_name), raising=False)
    planner_cls = getattr(planner_api, "PreventiveActionPlanner", None)
    if planner_cls is None:
        pytest.fail("P106 RED: expose PreventiveActionPlanner.", pytrace=False)

    planner = planner_cls()
    for route in ("allow", "deny", "escalate", "fallback"):
        result = planner.plan({"test_route": route, "simulation_only": True})
        assert getattr(result, "execution_enabled", result.get("execution_enabled")) is False
        assert getattr(result, "simulation_only", result.get("simulation_only")) is True
        assert getattr(result, "p107_required_for_execution", result.get("p107_required_for_execution")) is True

    assert touched == []
