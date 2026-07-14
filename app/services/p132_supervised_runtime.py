"""P132 supervisor manifest validation and local endurance qualification."""

from __future__ import annotations

import configparser
import json
import os
import plistlib
import re
import time
import tomllib
import tracemalloc
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p131_always_on_monitor import AlwaysOnMonitor, LocalJsonlSource, MonitorConfig, load_monitor_state

PROFILE_SCHEMA_VERSION = "p132.endurance_profile.v1"
ENDURANCE_REPORT_SCHEMA_VERSION = "p132.endurance_report.v1"
SUPERVISOR_VALIDATION_SCHEMA_VERSION = "p132.supervisor_validation.v1"
SYSTEMD_MANIFEST = "opscat-monitor.service"
LAUNCHD_MANIFEST = "io.opscat.monitor.plist"
COMPOSE_MANIFEST = "compose.monitor.yaml"
EXPECTED_CONSOLE_ENTRYPOINT = "app.monitor_cli:main"
EXPECTED_COMMAND = ("opscat-monitor", "run", "--config", "/etc/opscat/monitor.json", "--forever")
EXPECTED_COMPOSE_IMAGE = (
    "opscat-monitor@sha256:${OPSCAT_MONITOR_IMAGE_DIGEST:?set a 64-hex image manifest digest}"
)
FORBIDDEN_TEXT_TOKENS = (
    "secret",
    "password",
    "passwd",
    "token",
    "credential",
    "apikey",
    "api_key",
    "authorization",
    "bearer",
    "curl ",
    "wget ",
    "http://",
    "https://",
    " bash",
    "/bin/sh",
    "/bin/bash",
    " sh -c",
)


class P132SupervisorError(ValueError):
    """Raised when a P132 supervisor or endurance input fails closed."""


@dataclass
class _FakeClock:
    current: datetime

    def now(self) -> datetime:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)

    def monotonic(self) -> float:
        return self.current.timestamp()


def load_endurance_profile(path: Path | str) -> dict[str, Any]:
    """Load and validate the promoted local P132 endurance profile."""

    profile_path = Path(path)
    try:
        raw = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise P132SupervisorError("invalid_endurance_profile") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise P132SupervisorError("invalid_endurance_profile_schema")

    required_positive = (
        "backoff_attempts",
        "backoff_base_seconds",
        "backoff_cap_seconds",
        "canary_every_cycles",
        "cycle_count",
        "interval_seconds",
        "max_artifact_bytes",
        "max_bytes_per_cycle",
        "max_cpu_seconds",
        "max_line_bytes",
        "max_peak_memory_mib",
        "max_recent_observation_hashes",
        "max_records_per_cycle",
        "max_report_dir_bytes",
        "max_report_files",
        "max_shutdown_latency_seconds",
        "max_state_bytes",
        "max_wall_seconds",
        "min_artifact_free_bytes",
        "observation_count",
        "report_interval_seconds",
        "stable_window_seconds",
    )
    for key in required_positive:
        if type(raw.get(key)) is not int or int(raw[key]) <= 0:
            raise P132SupervisorError(f"invalid_profile_integer:{key}")
    if raw["cycle_count"] != 1000 or raw["observation_count"] != 1000:
        raise P132SupervisorError("profile_must_generate_exactly_1000_observations")
    expected = raw.get("expected_backoff_seconds")
    if not isinstance(expected, list) or any(type(value) is not int or value <= 0 for value in expected):
        raise P132SupervisorError("invalid_expected_backoff_seconds")
    calculated = [
        restart_backoff_seconds(
            attempt,
            base_seconds=int(raw["backoff_base_seconds"]),
            cap_seconds=int(raw["backoff_cap_seconds"]),
        )
        for attempt in range(1, int(raw["backoff_attempts"]) + 1)
    ]
    if expected != calculated:
        raise P132SupervisorError("expected_backoff_seconds_mismatch")
    if raw["max_line_bytes"] > raw["max_bytes_per_cycle"]:
        raise P132SupervisorError("profile_line_limit_exceeds_cycle_limit")
    return dict(raw)


def restart_backoff_seconds(attempt: int, *, base_seconds: int, cap_seconds: int) -> int:
    """Return deterministic capped exponential restart backoff for a 1-based attempt."""

    if type(attempt) is not int or attempt <= 0:
        raise ValueError("attempt_must_be_positive")
    if type(base_seconds) is not int or base_seconds <= 0:
        raise ValueError("base_seconds_must_be_positive")
    if type(cap_seconds) is not int or cap_seconds <= 0:
        raise ValueError("cap_seconds_must_be_positive")
    return min(cap_seconds, base_seconds * (2 ** (attempt - 1)))


def restart_attempt_after_window(attempt: int, *, runtime_seconds: int | float, stable_window_seconds: int | float) -> int:
    """Reset restart attempts after a stable runtime window, otherwise increment."""

    if type(attempt) is not int or attempt < 0:
        raise ValueError("attempt_must_be_nonnegative")
    if isinstance(runtime_seconds, bool) or not isinstance(runtime_seconds, (int, float)) or runtime_seconds < 0:
        raise ValueError("runtime_seconds_must_be_nonnegative")
    if isinstance(stable_window_seconds, bool) or not isinstance(stable_window_seconds, (int, float)) or stable_window_seconds <= 0:
        raise ValueError("stable_window_seconds_must_be_positive")
    return 0 if float(runtime_seconds) >= float(stable_window_seconds) else attempt + 1


def validate_supervisor_manifests(manifest_dir: Path | str, *, project_root: Path | str) -> dict[str, Any]:
    """Parse supervisor examples and return a fail-closed structural ledger."""

    root = Path(project_root).expanduser().resolve()
    entrypoint = _console_entrypoint(root / "pyproject.toml")
    manifest_root = Path(manifest_dir).expanduser().resolve()
    checks = {
        "systemd": _validate_systemd(manifest_root / SYSTEMD_MANIFEST),
        "launchd": _validate_launchd(manifest_root / LAUNCHD_MANIFEST),
        "compose": _validate_compose(manifest_root / COMPOSE_MANIFEST),
    }
    source_hashes = {
        (manifest_root / name).relative_to(root).as_posix(): _file_hash(manifest_root / name)
        for name in (SYSTEMD_MANIFEST, LAUNCHD_MANIFEST, COMPOSE_MANIFEST)
    }
    passed = entrypoint == EXPECTED_CONSOLE_ENTRYPOINT and all(checks.values())
    result: dict[str, Any] = {
        "schema_version": SUPERVISOR_VALIDATION_SCHEMA_VERSION,
        "passed": passed,
        "console_entrypoint": entrypoint,
        "manifests": checks,
        "source_hashes": source_hashes,
    }
    result["supervisor_validation_hash"] = stable_hash(result)
    return result


def run_endurance_qualification(profile: Mapping[str, Any], *, workspace: Path | str) -> dict[str, Any]:
    """Run the accelerated local P132 endurance qualification with injected time."""

    cycle_count = _profile_int(profile, "cycle_count")
    observation_count = _profile_int(profile, "observation_count")
    if cycle_count != 1000 or observation_count != 1000:
        raise P132SupervisorError("endurance_requires_exactly_1000_cycles_and_observations")

    workspace_path = Path(workspace).expanduser().resolve()
    workspace_path.mkdir(parents=True, exist_ok=True)
    source_path = workspace_path / "telemetry.jsonl"
    _write_observations(source_path, observation_count)
    config = _endurance_monitor_config(profile, workspace_path, source_path)
    clock = _FakeClock(datetime(2026, 7, 13, tzinfo=UTC))

    tracemalloc.start()
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    try:
        run_report = AlwaysOnMonitor(config, clock=clock).run(max_cycles=cycle_count, sleep_enabled=True)
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    cpu_seconds = time.process_time() - cpu_start
    wall_seconds = time.perf_counter() - wall_start

    reports = sorted(config.report_dir.glob("p131-health-*.json"))
    retained_reports = reports
    state = load_monitor_state(config.state_path, allowed_roots=config.allowed_artifact_roots)
    accepted = int(state["totals"]["accepted_observation_count"])
    duplicated = int(state["totals"]["duplicate_observation_count"])
    invalid = int(state["totals"]["source_failure_count"])
    lost = max(0, observation_count - accepted - duplicated - invalid)
    state_bytes = config.state_path.stat().st_size
    report_dir_bytes = _tree_size(config.report_dir)
    artifact_bytes = _tree_size(workspace_path)
    peak_mib = peak_bytes / (1024 * 1024)
    resource_gate_values = {
        "state_bytes": state_bytes,
        "report_dir_bytes": report_dir_bytes,
        "artifact_bytes": artifact_bytes,
        "tracemalloc_peak_bytes": peak_bytes,
        "tracemalloc_peak_mib": peak_mib,
        "cpu_seconds": cpu_seconds,
        "wall_seconds": wall_seconds,
    }
    resource_checks = {
        "state_bytes": state_bytes <= _profile_int(profile, "max_state_bytes"),
        "report_dir_bytes": report_dir_bytes <= _profile_int(profile, "max_report_dir_bytes"),
        "artifact_bytes": artifact_bytes <= _profile_int(profile, "max_artifact_bytes"),
        "tracemalloc_peak_mib": peak_mib <= _profile_int(profile, "max_peak_memory_mib"),
        "cpu_seconds": cpu_seconds <= _profile_int(profile, "max_cpu_seconds"),
        "wall_seconds": wall_seconds <= _profile_int(profile, "max_wall_seconds"),
        "retained_report_count": len(retained_reports) <= _profile_int(profile, "max_report_files"),
        "recent_hash_count": len(state.get("recent_observation_hashes", [])) <= _profile_int(profile, "max_recent_observation_hashes"),
    }
    resource_gates = {
        "passed": all(resource_checks.values()),
        "checks": resource_checks,
        "values": resource_gate_values,
    }
    source_hash = _file_hash(source_path)
    state_hash = _file_hash(config.state_path)
    report_hashes = {path.name: _file_hash(path) for path in retained_reports}

    report: dict[str, Any] = {
        "schema_version": ENDURANCE_REPORT_SCHEMA_VERSION,
        "profile_id": str(profile.get("profile_id", "")),
        "runtime_id": config.runtime_id,
        "config_hash": config.config_hash,
        "cycle_count": int(state["cycle_count"]),
        "accounting": {
            "expected": observation_count,
            "accepted": accepted,
            "invalid": invalid,
            "duplicated": duplicated,
            "lost": lost,
        },
        "retained_report_count": len(retained_reports),
        "resource_gates": resource_gates,
        "runtime_authority": run_report["authority"],
        "runtime_source": {
            "module": "app.services.p131_always_on_monitor",
            "class": "AlwaysOnMonitor",
            "self_hash": _file_hash(Path(__file__).with_name("p131_always_on_monitor.py")),
        },
        "evaluator_source": {
            "module": "app.services.p132_supervised_runtime",
            "self_hash": _file_hash(Path(__file__)),
        },
        "artifacts": {
            "workspace": str(workspace_path),
            "source_path": str(source_path),
            "state_path": str(config.state_path),
            "report_dir": str(config.report_dir),
            "source_hash": source_hash,
            "state_hash": state_hash,
            "report_hashes": report_hashes,
        },
        "profile_gates": {
            "max_report_files": _profile_int(profile, "max_report_files"),
            "max_report_dir_bytes": _profile_int(profile, "max_report_dir_bytes"),
            "max_state_bytes": _profile_int(profile, "max_state_bytes"),
            "max_artifact_bytes": _profile_int(profile, "max_artifact_bytes"),
            "max_cpu_seconds": _profile_int(profile, "max_cpu_seconds"),
            "max_wall_seconds": _profile_int(profile, "max_wall_seconds"),
            "max_peak_memory_mib": _profile_int(profile, "max_peak_memory_mib"),
        },
        "evaluator_authority": {
            "child_process_launch_count": 0,
            "sigterm_count": 0,
            "sigint_count": 0,
            "forced_kill_count": 0,
            "watchdog_call_count": 0,
            "status_call_count": 0,
            "lease_conflict_count": 0,
            "arbitrary_command_count": 0,
            "credential_read_count": 0,
            "network_call_count": 0,
            "connector_write_count": 0,
            "remediation_count": 0,
            "staging_mutation_count": 0,
            "production_mutation_count": 0,
        },
    }
    report["endurance_report_hash"] = stable_hash(report)
    return report


def _console_entrypoint(pyproject_path: Path) -> str | None:
    try:
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    project = data.get("project")
    scripts = project.get("scripts") if isinstance(project, Mapping) else None
    value = scripts.get("opscat-monitor") if isinstance(scripts, Mapping) else None
    return value if isinstance(value, str) else None


def _validate_systemd(path: Path) -> bool:
    try:
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        with path.open(encoding="utf-8") as handle:
            parser.read_file(handle)
    except (OSError, configparser.Error):
        return False
    if not parser.has_section("Service"):
        return False
    service = parser["Service"]
    unit = parser["Unit"] if parser.has_section("Unit") else {}
    exec_start = service.get("ExecStart", "")
    command = tuple(exec_start.split())
    return all(
        (
            _safe_text(exec_start),
            command == EXPECTED_COMMAND,
            service.get("Restart") == "always",
            _positive_seconds(service.get("RestartSec")),
            _positive_seconds(unit.get("StartLimitIntervalSec")),
            _positive_int_text(unit.get("StartLimitBurst")),
            service.get("StartLimitIntervalSec") is None,
            service.get("StartLimitBurst") is None,
            _positive_seconds(service.get("TimeoutStopSec")),
            service.get("KillSignal") in {"SIGTERM", "SIGINT"},
            service.get("NoNewPrivileges") == "true",
            service.get("PrivateTmp") == "true",
            service.get("ProtectSystem") in {"strict", "full"},
            service.get("User") not in {None, "", "root"},
        )
    )


def _validate_launchd(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            data = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException):
        return False
    if not isinstance(data, Mapping):
        return False
    arguments = data.get("ProgramArguments")
    if not isinstance(arguments, list) or tuple(arguments) != EXPECTED_COMMAND:
        return False
    if not _safe_text(json.dumps(data, sort_keys=True)):
        return False
    return all(
        (
            data.get("Label") == "io.opscat.monitor",
            data.get("RunAtLoad") is True,
            data.get("KeepAlive") is True,
            _positive_int(data.get("ThrottleInterval")),
            _positive_int(data.get("ExitTimeOut")),
            isinstance(data.get("StandardOutPath"), str),
            isinstance(data.get("StandardErrorPath"), str),
        )
    )


def _validate_compose(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(data, Mapping) or not _safe_text(json.dumps(data, sort_keys=True)):
        return False
    services = data.get("services")
    service = services.get("opscat-monitor") if isinstance(services, Mapping) else None
    if not isinstance(service, Mapping):
        return False
    command = service.get("command")
    image = service.get("image")
    volumes = service.get("volumes")
    security_opt = service.get("security_opt")
    deploy = service.get("deploy")
    restart_policy = deploy.get("restart_policy") if isinstance(deploy, Mapping) else None
    return all(
        (
            isinstance(command, list) and tuple(command) == EXPECTED_COMMAND[1:],
            _immutable_image(image),
            service.get("restart") == "always",
            isinstance(restart_policy, Mapping),
            isinstance(restart_policy, Mapping) and restart_policy.get("condition") == "any",
            isinstance(restart_policy, Mapping) and _positive_seconds_object(restart_policy.get("delay")),
            isinstance(restart_policy, Mapping) and _positive_int(restart_policy.get("max_attempts")),
            isinstance(restart_policy, Mapping) and _positive_seconds_object(restart_policy.get("window")),
            _positive_seconds_object(service.get("stop_grace_period")),
            service.get("privileged") is False,
            service.get("network_mode") in {None, "none"},
            service.get("read_only") is True,
            service.get("user") not in {None, "", "0", "root"},
            isinstance(volumes, list) and any("/etc/opscat/monitor.json:ro" in str(volume) for volume in volumes),
            isinstance(security_opt, list) and "no-new-privileges:true" in security_opt,
            "environment" not in service,
            "env_file" not in service,
            "secrets" not in service,
        )
    )


def _immutable_image(value: object) -> bool:
    if value == EXPECTED_COMPOSE_IMAGE:
        return True
    if not isinstance(value, str) or value.count("@sha256:") != 1 or "$" in value:
        return False
    repository, digest = value.rsplit("@sha256:", 1)
    return bool(repository.strip()) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None


def _safe_text(value: str) -> bool:
    lowered = f" {value.lower()} "
    return not any(token in lowered for token in FORBIDDEN_TEXT_TOKENS)


def _positive_seconds(value: str | None) -> bool:
    if value is None:
        return False
    return _positive_int_text(value.removesuffix("s"))


def _positive_seconds_object(value: object) -> bool:
    return isinstance(value, str) and _positive_seconds(value)


def _positive_int_text(value: str | None) -> bool:
    if value is None or not value.isdecimal():
        return False
    return int(value) > 0


def _positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def _write_observations(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for index in range(count):
            row = {
                "event_id": f"p132-event-{index:04d}",
                "service": "checkout",
                "message": "ok",
                "sequence": index,
            }
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=True) + "\n")


def _endurance_monitor_config(profile: Mapping[str, Any], workspace: Path, source_path: Path) -> MonitorConfig:
    return MonitorConfig(
        config_hash=stable_hash(
            {
                "schema_version": "p131.monitor_config.v1",
                "runtime_id": "p132-endurance-runtime",
                "interval_seconds": _profile_int(profile, "interval_seconds"),
                "daily_report_interval_seconds": _profile_int(profile, "report_interval_seconds"),
                "max_report_files": _profile_int(profile, "max_report_files"),
                "max_report_dir_bytes": _profile_int(profile, "max_report_dir_bytes"),
                "min_artifact_free_bytes": _profile_int(profile, "min_artifact_free_bytes"),
                "source_hash": _file_hash(source_path),
            }
        ),
        runtime_id="p132-endurance-runtime",
        interval_seconds=_profile_int(profile, "interval_seconds"),
        heartbeat_timeout_seconds=3,
        data_stale_after_seconds=30,
        daily_report_interval_seconds=_profile_int(profile, "report_interval_seconds"),
        canary_every_cycles=_profile_int(profile, "canary_every_cycles"),
        max_consecutive_failures=3,
        max_bytes_per_cycle=_profile_int(profile, "max_bytes_per_cycle"),
        max_records_per_cycle=1,
        max_line_bytes=_profile_int(profile, "max_line_bytes"),
        max_report_files=_profile_int(profile, "max_report_files"),
        max_report_dir_bytes=_profile_int(profile, "max_report_dir_bytes"),
        min_artifact_free_bytes=_profile_int(profile, "min_artifact_free_bytes"),
        state_path=workspace / "state.json",
        report_dir=workspace / "reports",
        lease_path=workspace / "runtime.lock",
        termination_receipt_path=workspace / "termination-receipt.json",
        allowed_data_roots=(workspace,),
        allowed_artifact_roots=(workspace,),
        sources=(
            LocalJsonlSource(
                source_id="local",
                path=source_path,
                allowed_root=workspace,
                relative_path=source_path.relative_to(workspace),
                enabled=True,
            ),
        ),
    )


def _tree_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    if not path.exists():
        return total
    for root, _, files in os.walk(path):
        for filename in files:
            file_path = Path(root) / filename
            if file_path.is_file() and not file_path.is_symlink():
                total += file_path.stat().st_size
    return total


def _file_hash(path: Path) -> str:
    return stable_hash(path.read_bytes().hex())


def _profile_int(profile: Mapping[str, Any], key: str) -> int:
    value = profile.get(key)
    if type(value) is not int or value <= 0:
        raise P132SupervisorError(f"invalid_profile_integer:{key}")
    return value
