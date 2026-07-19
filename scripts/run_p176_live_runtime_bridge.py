#!/usr/bin/env python3
"""Run the P176 runtime bridge, then materialize and qualify live evidence."""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class P176RuntimeBridgeCliError(RuntimeError):
    """Raised when the defensive runtime bridge CLI cannot continue safely."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--target-endpoint", required=True)
    parser.add_argument("--observer-endpoint", required=True)
    parser.add_argument("--reviewed-apply-plan-artifact", type=Path)
    parser.add_argument("--reviewed-teardown-plan-artifact", type=Path)
    parser.add_argument("--reviewed-cost-cutoff-apply-plan-artifact", type=Path)
    parser.add_argument("--reviewed-cost-cutoff-destroy-plan-artifact", type=Path)
    args = parser.parse_args(argv)

    try:
        result = run_runtime_bridge(
            run_dir=args.run_dir,
            target_endpoint=args.target_endpoint,
            observer_endpoint=args.observer_endpoint,
            reviewed_apply_plan_artifact=args.reviewed_apply_plan_artifact,
            reviewed_teardown_plan_artifact=args.reviewed_teardown_plan_artifact,
            reviewed_cost_cutoff_apply_plan_artifact=args.reviewed_cost_cutoff_apply_plan_artifact,
            reviewed_cost_cutoff_destroy_plan_artifact=args.reviewed_cost_cutoff_destroy_plan_artifact,
        )
    except (P176RuntimeBridgeCliError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(
            json.dumps(
                {
                    "phase": "p176",
                    "status": "blocked",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    print(json.dumps({"phase": "p176", **result}, sort_keys=True))
    return 0


def run_runtime_bridge(
    *,
    run_dir: Path,
    target_endpoint: str,
    observer_endpoint: str,
    reviewed_apply_plan_artifact: Path | None = None,
    reviewed_teardown_plan_artifact: Path | None = None,
    reviewed_cost_cutoff_apply_plan_artifact: Path | None = None,
    reviewed_cost_cutoff_destroy_plan_artifact: Path | None = None,
) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    service_result = _invoke_runtime_service(
        run_dir=run_dir,
        target_endpoint=target_endpoint,
        observer_endpoint=observer_endpoint,
    )
    service_payload = _jsonable(service_result)
    if not isinstance(service_payload, Mapping):
        raise P176RuntimeBridgeCliError("runtime service result is not an object")
    service_status = service_payload.get("status")
    if service_status == "runtime_collection_complete":
        return {
            "status": "runtime_collection_complete",
            "run_dir": str(run_dir),
            "runtime_service": service_payload,
        }
    if service_status != "runtime_finalization_complete":
        raise P176RuntimeBridgeCliError("runtime service returned unsupported lifecycle status")

    bridge = _run_existing_script(
        "run_p176_live_bridge.py",
        _plan_artifact_args(
            run_dir=run_dir,
            reviewed_apply_plan_artifact=reviewed_apply_plan_artifact,
            reviewed_teardown_plan_artifact=reviewed_teardown_plan_artifact,
            reviewed_cost_cutoff_apply_plan_artifact=reviewed_cost_cutoff_apply_plan_artifact,
            reviewed_cost_cutoff_destroy_plan_artifact=reviewed_cost_cutoff_destroy_plan_artifact,
        ),
    )
    qualification = _run_existing_script(
        "run_p176_live_qualification.py",
        _plan_artifact_args(
            run_dir=run_dir,
            reviewed_apply_plan_artifact=reviewed_apply_plan_artifact,
            reviewed_teardown_plan_artifact=reviewed_teardown_plan_artifact,
            reviewed_cost_cutoff_apply_plan_artifact=reviewed_cost_cutoff_apply_plan_artifact,
            reviewed_cost_cutoff_destroy_plan_artifact=reviewed_cost_cutoff_destroy_plan_artifact,
        ),
    )

    return {
        "status": "runtime_bridge_complete",
        "run_dir": str(run_dir),
        "runtime_service": service_payload,
        "live_bridge": bridge,
        "live_qualification": qualification,
    }


def _invoke_runtime_service(*, run_dir: Path, target_endpoint: str, observer_endpoint: str) -> Any:
    try:
        module = importlib.import_module("app.services.p176_runtime_bridge")
    except ModuleNotFoundError as exc:
        if exc.name == "app.services.p176_runtime_bridge":
            raise P176RuntimeBridgeCliError("runtime service module is missing") from exc
        raise

    for name in ("run_p176_runtime_bridge", "run_runtime_bridge", "execute_runtime_bridge", "main"):
        candidate = getattr(module, name, None)
        if callable(candidate):
            return _call_service(candidate, run_dir=run_dir, target_endpoint=target_endpoint, observer_endpoint=observer_endpoint)
    raise P176RuntimeBridgeCliError("runtime service entrypoint is missing")


def _call_service(
    candidate: Callable[..., Any],
    *,
    run_dir: Path,
    target_endpoint: str,
    observer_endpoint: str,
) -> Any:
    signature = inspect.signature(candidate)
    kwargs = {
        "run_dir": run_dir,
        "target_endpoint": target_endpoint,
        "observer_endpoint": observer_endpoint,
    }
    parameters = signature.parameters
    supported_names = set(kwargs)
    has_var_keyword = any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())
    has_var_positional = any(parameter.kind is inspect.Parameter.VAR_POSITIONAL for parameter in parameters.values())
    required_extra = {
        name
        for name, parameter in parameters.items()
        if name not in supported_names
        and parameter.kind not in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
        and parameter.default is inspect.Parameter.empty
    }
    named_parameters = {
        name: parameter
        for name, parameter in parameters.items()
        if parameter.kind not in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
    }
    valid_named_contract = set(named_parameters) == supported_names and all(
        parameter.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        for parameter in named_parameters.values()
    )
    if has_var_positional or required_extra or (not has_var_keyword and not valid_named_contract):
        raise P176RuntimeBridgeCliError("runtime service signature mismatch")
    try:
        signature.bind(**kwargs)
    except TypeError as exc:
        raise P176RuntimeBridgeCliError("runtime service signature mismatch") from exc
    return candidate(**kwargs)


def _plan_artifact_args(
    *,
    run_dir: Path,
    reviewed_apply_plan_artifact: Path | None,
    reviewed_teardown_plan_artifact: Path | None,
    reviewed_cost_cutoff_apply_plan_artifact: Path | None,
    reviewed_cost_cutoff_destroy_plan_artifact: Path | None,
) -> list[str]:
    args = ["--run-dir", str(run_dir)]
    optional = (
        ("--reviewed-apply-plan-artifact", reviewed_apply_plan_artifact),
        ("--reviewed-teardown-plan-artifact", reviewed_teardown_plan_artifact),
        ("--reviewed-cost-cutoff-apply-plan-artifact", reviewed_cost_cutoff_apply_plan_artifact),
        ("--reviewed-cost-cutoff-destroy-plan-artifact", reviewed_cost_cutoff_destroy_plan_artifact),
    )
    for flag, value in optional:
        if value is not None:
            args.extend([flag, str(value)])
    return args


def _run_existing_script(script_name: str, args: list[str]) -> Mapping[str, Any]:
    script = ROOT / "scripts" / script_name
    completed = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise P176RuntimeBridgeCliError(f"{script_name} failed with exit code {completed.returncode}")
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise P176RuntimeBridgeCliError(f"{script_name} produced no JSON output")
    try:
        value = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise P176RuntimeBridgeCliError(f"{script_name} produced invalid JSON") from exc
    if not isinstance(value, Mapping):
        raise P176RuntimeBridgeCliError(f"{script_name} JSON output is not an object")
    return value


def _jsonable(value: Any) -> Any:
    if hasattr(value, "as_dict") and callable(value.as_dict):
        return _jsonable(value.as_dict())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return repr(value)


if __name__ == "__main__":
    raise SystemExit(main())
