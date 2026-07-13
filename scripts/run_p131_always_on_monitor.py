#!/usr/bin/env python3
"""Generate deterministic P131 runtime, watchdog, and release evidence."""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p110_evaluation import stable_hash  # noqa: E402
from app.services.p131_always_on_monitor import AlwaysOnMonitor, evaluate_watchdog, load_monitor_config, load_monitor_state, monitor_status_snapshot  # noqa: E402
from app.services.p131_release_evidence import P131_READY_STATUS, build_p131_release_evidence, validate_p131_release_evidence  # noqa: E402


class EvidenceClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 7, 13, tzinfo=UTC)
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += timedelta(seconds=seconds)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=Path, default=ROOT / "evals/p131/input/scenario.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evals/p131")
    args = parser.parse_args(argv)
    scenario = _read_json(args.scenario)
    rows = scenario.get("telemetry_rows")
    if not isinstance(rows, list) or len(rows) != 2 or not all(isinstance(row, Mapping) for row in rows):
        raise ValueError("scenario_requires_two_telemetry_rows")

    with tempfile.TemporaryDirectory(prefix="opscat-p131-") as temporary_name:
        temporary = Path(temporary_name)
        source = temporary / "telemetry.jsonl"
        _write_jsonl(source, rows[:1])
        config_path = temporary / "monitor-config.json"
        config = {
            "schema_version": "p131.monitor_config.v1",
            "runtime_id": "p131-release-runtime",
            "interval_seconds": 60,
            "heartbeat_timeout_seconds": 180,
            "data_stale_after_seconds": 300,
            "daily_report_interval_seconds": 120,
            "canary_every_cycles": 1,
            "max_consecutive_failures": 3,
            "state_path": str(temporary / "runtime-state.json"),
            "report_dir": str(temporary / "reports"),
            "lease_path": str(temporary / "runtime.lock"),
            "allowed_data_roots": [str(temporary)],
            "sources": [{"source_id": "release-jsonl", "kind": "local_jsonl", "path": str(source), "enabled": True}],
        }
        _write_atomic(config_path, config)
        clock = EvidenceClock()
        first = AlwaysOnMonitor(load_monitor_config(config_path), clock=clock).run(max_cycles=2, sleep_enabled=True)
        _append_jsonl(source, rows[1])
        second = AlwaysOnMonitor(load_monitor_config(config_path), clock=clock).run(max_cycles=1, sleep_enabled=False)
        state_path = temporary / "runtime-state.json"
        state = load_monitor_state(state_path)
        status = monitor_status_snapshot(state_path, now=clock.now(), heartbeat_timeout_seconds=180, data_stale_after_seconds=300)

        tampered_path = temporary / "tampered-state.json"
        tampered = dict(state)
        tampered["cycle_count"] = 999
        _write_atomic(tampered_path, tampered)
        watchdog_matrix = {
            "schema_version": "p131.watchdog_matrix.v1",
            "cases": {
                "current": _sanitize_watchdog(evaluate_watchdog(state_path, now=clock.now(), heartbeat_timeout_seconds=180)),
                "missing": _sanitize_watchdog(evaluate_watchdog(temporary / "missing.json", now=clock.now(), heartbeat_timeout_seconds=180)),
                "stale": _sanitize_watchdog(evaluate_watchdog(state_path, now=clock.now() + timedelta(seconds=181), heartbeat_timeout_seconds=180)),
                "tampered": _sanitize_watchdog(evaluate_watchdog(tampered_path, now=clock.now(), heartbeat_timeout_seconds=180)),
            },
        }
        runtime_report = {
            "schema_version": "p131.runtime_evidence.v1",
            "scenario_hash": stable_hash(scenario),
            "sleep_intervals_seconds": clock.sleeps,
            "real_time_bounded_smoke_passed": _real_time_scheduler_smoke(temporary, source),
            "first_run": _summary(first),
            "restart_run": _summary(second),
            "static_boundary": _static_boundary_report(),
            "final_state": {
                "cycle_count": state["cycle_count"],
                "resume_count": state["resume_count"],
                "accepted_observation_count": state["totals"]["accepted_observation_count"],
                "duplicate_observation_count": state["totals"]["duplicate_observation_count"],
                "ready": status["ready"],
                "reasons": status["reasons"],
                "canary": state["canary"],
                "totals": state["totals"],
                "authority": state["authority"],
            },
        }
        runtime_report["runtime_report_hash"] = stable_hash(runtime_report)
        watchdog_matrix["watchdog_matrix_hash"] = stable_hash(watchdog_matrix)
        release = build_p131_release_evidence(runtime_report, watchdog_matrix)
        validate_p131_release_evidence(release, runtime_report=runtime_report, watchdog_matrix=watchdog_matrix)

    output_dir = args.output_dir.resolve()
    _write_atomic(output_dir / "runtime-report.json", runtime_report)
    _write_atomic(output_dir / "watchdog-matrix.json", watchdog_matrix)
    _write_atomic(output_dir / "release-evidence.json", release)
    print(json.dumps({"release_status": release["release_status"], "release_evidence_hash": release["release_evidence_hash"]}, sort_keys=True))
    return 0 if release["release_status"] == P131_READY_STATUS else 1


def _summary(report: Mapping[str, Any]) -> dict[str, Any]:
    value = report.get("summary")
    return dict(value) if isinstance(value, Mapping) else {}


def _sanitize_watchdog(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != "state_hash"}


def _static_boundary_report() -> dict[str, Any]:
    paths = [
        ROOT / "app/services/p131_always_on_monitor.py",
        ROOT / "app/services/p131_release_evidence.py",
        ROOT / "app/monitor_cli.py",
        ROOT / "app/api/health.py",
        ROOT / "app/config.py",
        ROOT / "scripts/run_p131_always_on_monitor.py",
    ]
    forbidden_imports = {"boto3", "httpx", "kubernetes", "requests", "socket", "subprocess", "urllib"}
    forbidden_calls = {"eval", "exec", "os.popen", "os.system", "subprocess.Popen", "subprocess.call", "subprocess.run"}
    findings: list[str] = []
    source_hashes: dict[str, str] = {}
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        source_hashes[relative] = stable_hash(text)
        tree = ast.parse(text, filename=relative)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in forbidden_imports:
                        findings.append(f"{relative}:{node.lineno}:import:{alias.name}")
            elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in forbidden_imports:
                findings.append(f"{relative}:{node.lineno}:import:{node.module}")
            elif isinstance(node, ast.Call):
                name = _call_name(node.func)
                if name in forbidden_calls:
                    findings.append(f"{relative}:{node.lineno}:call:{name}")
    return {"source_hashes": source_hashes, "forbidden_matches": sorted(findings)}


def _real_time_scheduler_smoke(temporary: Path, source: Path) -> bool:
    config_path = temporary / "real-time-config.json"
    config = {
        "schema_version": "p131.monitor_config.v1",
        "runtime_id": "p131-real-time-smoke",
        "interval_seconds": 1,
        "heartbeat_timeout_seconds": 3,
        "data_stale_after_seconds": 3,
        "daily_report_interval_seconds": 1,
        "canary_every_cycles": 1,
        "max_consecutive_failures": 3,
        "state_path": str(temporary / "real-time-state.json"),
        "report_dir": str(temporary / "real-time-reports"),
        "lease_path": str(temporary / "real-time.lock"),
        "allowed_data_roots": [str(temporary)],
        "sources": [{"source_id": "real-time-jsonl", "kind": "local_jsonl", "path": str(source), "enabled": True}],
    }
    _write_atomic(config_path, config)
    started = time.monotonic()
    report = AlwaysOnMonitor(load_monitor_config(config_path)).run(max_cycles=2, sleep_enabled=True)
    elapsed = time.monotonic() - started
    return report["summary"]["cycle_count"] == 2 and 0.75 <= elapsed <= 5.0


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("invalid_scenario")
    return value


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(dict(row), sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(row), sort_keys=True) + "\n")


def _write_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
