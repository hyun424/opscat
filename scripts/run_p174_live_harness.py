"""CLI wrapper for the deterministic P174 live qualification harness."""

from __future__ import annotations

import argparse
import json
import math
import os
import stat
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlsplit

from app.services.p174_gcp_provider_lab import (
    ACTION_SCHEMA_VERSION,
    HttpP174ProviderTransport,
    P174ProviderLabError,
    ProviderActionRequest,
    ProviderLab,
    ProviderManifest,
    validate_manifest,
)
from app.services.p174_live_harness import (
    MAX_BASELINE_STABILIZATION_ATTEMPTS,
    JsonlEvidenceRecorder,
    P174LiveHarnessError,
    ScenarioStep,
    ScheduleStep,
    load_reviewed_manifest,
    run_qualification,
    stable_hash,
)


class _CliError(ValueError):
    pass


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _CliError(message)


_AUTHORITY_FIELDS = frozenset(
    {
        "P174_ACTION_CAPABILITY",
        "P174_FAULT_CAPABILITY",
        "P174_PROJECT_ID",
        "P174_TARGET_ID",
        "P174_RUN_ID",
        "P174_POLICY_VERSION",
    }
)
_AUTHORITY_FILE_MAX_BYTES = 16 * 1024
_CAPABILITY_MIN_LENGTH = 32
_CAPABILITY_MAX_LENGTH = 512
_POLICY_VERSION = "p174-policy-v1"
_MIN_LIVE_WINDOW_INTERVAL_SECONDS = 15.0
_MIN_EVALUATION_DELTA_SECONDS = 14.0
_SCENARIO_READY_ATTEMPTS = MAX_BASELINE_STABILIZATION_ATTEMPTS
_SCENARIO_READY_INTERVAL_SECONDS = 1.0
_PROTECTED_RUNTIME_STATE_FIELDS = (
    "project_id",
    "target_id",
    "run_id",
    "pool_size",
    "canary_version",
    "worker_restart_generation",
    "worker_paused_until",
)


@dataclass(frozen=True)
class _Authority:
    action_capability: str
    fault_capability: str
    project_id: str
    target_id: str
    run_id: str
    policy_version: str


class LoopbackObserverClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 5.0,
        min_interval_seconds: float = _MIN_LIVE_WINDOW_INTERVAL_SECONDS,
        scenario_ready_attempts: int = _SCENARIO_READY_ATTEMPTS,
        scenario_ready_interval_seconds: float = _SCENARIO_READY_INTERVAL_SECONDS,
        sleep_fn: Callable[[float], None] | None = None,
        monotonic_fn: Callable[[], float] | None = None,
    ) -> None:
        self._base_url = _validate_loopback_base_url(base_url, "observer_endpoint")
        self._timeout_seconds = timeout_seconds
        if not math.isfinite(min_interval_seconds) or min_interval_seconds < _MIN_LIVE_WINDOW_INTERVAL_SECONDS:
            raise _CliError("observer_min_interval_must_be_at_least_15")
        if not isinstance(scenario_ready_attempts, int) or isinstance(scenario_ready_attempts, bool) or scenario_ready_attempts < 1 or scenario_ready_attempts > MAX_BASELINE_STABILIZATION_ATTEMPTS:
            raise _CliError("scenario_ready_attempts_invalid")
        if not math.isfinite(scenario_ready_interval_seconds) or scenario_ready_interval_seconds <= 0:
            raise _CliError("scenario_ready_interval_invalid")
        self._min_interval_seconds = min_interval_seconds
        self._scenario_ready_attempts = scenario_ready_attempts
        self._scenario_ready_interval_seconds = scenario_ready_interval_seconds
        self._sleep = sleep_fn or time.sleep
        self._monotonic = monotonic_fn or time.monotonic
        self._last_window_request_at: float | None = None
        self._last_evaluation_timestamp: float | None = None
        self._last_receipt_sequence: int | None = None
        self._seen_window_ids: set[str] = set()

    def observe_health_window(self, step: ScheduleStep) -> Mapping[str, Any]:
        self._pace_health_window()
        payload = self._get_json("/collect")
        window_id, timestamp, sequence = self._validate_window(payload)
        state = _collect_state(payload)
        return {
            "healthy": _collect_healthy(payload),
            "window_id": window_id,
            "timestamp": timestamp,
            "sequence": sequence,
            "state": state,
            "state_hash": stable_hash(state),
        }

    def observe_scenario(self, step: ScenarioStep) -> Mapping[str, Any]:
        observation: dict[str, Any] | None = None
        for attempt in range(1, self._scenario_ready_attempts + 1):
            payload = self._get_json("/collect")
            state = _collect_state(payload)
            ready = _collect_healthy(payload)
            observation = {
                "ready": ready,
                "stabilization_attempts": attempt,
                "state": state,
                "state_hash": stable_hash(state),
            }
            if ready:
                return observation
            if attempt < self._scenario_ready_attempts:
                self._sleep(self._scenario_ready_interval_seconds)
        assert observation is not None
        return observation

    def _get_json(self, path: str) -> dict[str, Any]:
        return _request_loopback_json(self._base_url, path, method="GET", timeout_seconds=self._timeout_seconds)

    def _pace_health_window(self) -> None:
        now = self._monotonic()
        if self._last_window_request_at is not None:
            remaining = self._min_interval_seconds - (now - self._last_window_request_at)
            if remaining > 0:
                self._sleep(remaining)
                now = self._monotonic()
        self._last_window_request_at = now

    def _validate_window(self, payload: Mapping[str, Any]) -> tuple[str, str, int]:
        evaluation = payload.get("evaluation")
        if not isinstance(evaluation, Mapping):
            raise _CliError("observer_evaluation_missing")
        raw_timestamp = evaluation.get("ts")
        if not isinstance(raw_timestamp, int | float) or isinstance(raw_timestamp, bool) or not math.isfinite(raw_timestamp):
            raise _CliError("observer_evaluation_timestamp_invalid")
        timestamp = float(raw_timestamp)
        if self._last_evaluation_timestamp is not None and timestamp - self._last_evaluation_timestamp < _MIN_EVALUATION_DELTA_SECONDS:
            raise _CliError("observer_evaluation_timestamp_too_rapid")

        receipts = payload.get("receipts")
        if not isinstance(receipts, Sequence) or isinstance(receipts, (str, bytes, bytearray)) or not receipts:
            raise _CliError("observer_receipts_missing")
        tail = receipts[-1]
        if not isinstance(tail, Mapping):
            raise _CliError("observer_receipt_tail_invalid")
        sequence = tail.get("sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
            raise _CliError("observer_receipt_sequence_invalid")
        if self._last_receipt_sequence is not None and sequence <= self._last_receipt_sequence:
            raise _CliError("observer_receipt_sequence_not_increasing")
        receipt_hash = tail.get("receipt_hash")
        if not isinstance(receipt_hash, str):
            raise _CliError("observer_receipt_hash_invalid")
        digest = receipt_hash.removeprefix("sha256:")
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise _CliError("observer_receipt_hash_invalid")
        receipt_hash = f"sha256:{digest}"

        window_id = stable_hash({"evaluation_timestamp": timestamp, "receipt_sequence_tail": sequence, "receipt_hash": receipt_hash})
        if window_id in self._seen_window_ids:
            raise _CliError("observer_window_duplicate")
        try:
            timestamp_text = datetime.fromtimestamp(timestamp, tz=UTC).isoformat().replace("+00:00", "Z")
        except (OverflowError, OSError, ValueError) as exc:
            raise _CliError("observer_evaluation_timestamp_invalid") from exc
        self._seen_window_ids.add(window_id)
        self._last_evaluation_timestamp = timestamp
        self._last_receipt_sequence = sequence
        return window_id, timestamp_text, sequence


class ProviderLabActionClient:
    def __init__(
        self,
        *,
        target_url: str,
        lab: ProviderLab,
        owner_id: str,
        fault_capability: str,
        policy_version: str,
        lease_expires_at: datetime,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._target_url = _validate_private_or_loopback_base_url(target_url, "action_endpoint")
        self._lab = lab
        self._owner_id = owner_id
        self._fault_capability = fault_capability
        self._policy_version = policy_version
        self._lease_expires_at = lease_expires_at
        self._timeout_seconds = timeout_seconds
        self._fault_cleanups: dict[str, dict[str, str]] = {}
        self._target_time = datetime.now(tz=UTC)

    def inject_fault(self, step: ScenarioStep, baseline: Mapping[str, Any]) -> Mapping[str, Any]:
        self._renew_authority()
        baseline_state = self._target_state()
        payload = _fault_body(
            step,
            self._lab.manifest,
            baseline_state=baseline_state,
            evidence_hash=stable_hash({"step": step.to_dict(), "baseline": baseline}),
            policy_version=self._policy_version,
            created_at=self._target_time,
        )
        result = _request_loopback_json(
            self._target_url,
            "/faults",
            method="POST",
            payload=payload,
            headers=self._fault_headers(),
            timeout_seconds=self._timeout_seconds,
        )
        evidence = result.get("evidence")
        if not isinstance(evidence, Mapping):
            raise _CliError("fault_evidence_missing")
        cleanup_token = evidence.get("cleanup_token")
        if not isinstance(cleanup_token, str) or not cleanup_token.startswith("sha256:"):
            raise _CliError("fault_cleanup_token_missing")
        self._fault_cleanups[step.campaign_hash] = {
            "original_request_id": str(payload["request_id"]),
            "original_idempotency_key": str(payload["idempotency_key"]),
            "cleanup_token": cleanup_token,
        }
        try:
            receipt_state = result.get("state")
            receipt_metrics = result.get("after_metrics")
            if not isinstance(receipt_state, Mapping) or not isinstance(receipt_metrics, Mapping):
                raise _CliError("fault_receipt_state_missing")
            state = _collect_state({"state": receipt_state, "metrics": receipt_metrics})
        except Exception as receipt_exc:
            cleanup_probe = {"status": "fault_receipt_validation_failed", "error_type": type(receipt_exc).__name__}
            try:
                cleanup_result = self.cleanup_scenario(step, baseline, cleanup_probe)
            except Exception as cleanup_exc:
                raise _CliError(
                    f"fault_receipt_validation_failed:{type(receipt_exc).__name__};cleanup_failed:{type(cleanup_exc).__name__}"
                ) from receipt_exc
            if not _runtime_cleanup_proven(baseline_state, cleanup_result):
                raise _CliError(f"fault_receipt_validation_failed:{type(receipt_exc).__name__};cleanup_unproven") from receipt_exc
            raise _CliError(f"fault_receipt_validation_failed:{type(receipt_exc).__name__};cleanup:proven") from receipt_exc
        return {
            "accepted": result.get("accepted", True) is not False,
            "baseline_state": baseline_state,
            "baseline_state_hash": stable_hash(baseline_state),
            "state": state,
            "state_hash": stable_hash(state),
            "receipt_hash": stable_hash(result),
        }

    def run_scenario(self, step: ScenarioStep, baseline: Mapping[str, Any], fault_result: Mapping[str, Any]) -> Mapping[str, Any]:
        self._renew_authority()
        before_state = self._target_state()
        request_target = self._lab.manifest.target_id
        if step.scenario.expected_outcome == "blocked_no_mutation":
            request_target = f"{request_target}-boundary"
        request = ProviderActionRequest(
            schema_version=ACTION_SCHEMA_VERSION,
            request_id=_scenario_request_key("action", step),
            idempotency_key=_scenario_request_key("action", step),
            project_id=self._lab.manifest.project_id,
            target_id=request_target,
            run_id=self._lab.manifest.run_id,
            action=step.scenario.action,
            parameters=_action_parameters(step, before_state),
            evidence_hash=stable_hash({"step": step.to_dict(), "fault": fault_result}),
            policy_version=self._policy_version,
            created_at=self._target_time,
        )
        try:
            receipt = self._lab.run_action(self._owner_id, request)
        except P174ProviderLabError as exc:
            reason = str(exc)
            if step.scenario.expected_outcome == "rejected" and reason == "action_not_allowed":
                receipt = {"status": "rejected", "failure_reason": reason}
            elif step.scenario.expected_outcome == "blocked_no_mutation" and reason == "target_not_allowed":
                receipt = {"status": "blocked", "failure_reason": reason}
            else:
                raise
        state = self._target_state()
        return {
            "accepted": receipt.get("status") in {"applied", "rolled_back"},
            "status": receipt.get("status"),
            "before_state_hash": stable_hash(before_state),
            "state": state,
            "state_hash": stable_hash(state),
            "receipt_hash": receipt.get("receipt_hash", stable_hash(receipt)),
            "failure_reason": receipt.get("failure_reason"),
            "failure_detail": receipt.get("failure_detail"),
            "state_sequence": receipt.get("state_sequence"),
            "irreversible_action": receipt.get("irreversible_action"),
            "rollback_closure_claimed": receipt.get("rollback_closure_claimed"),
        }

    def cleanup_scenario(self, step: ScenarioStep, baseline: Mapping[str, Any], post_result: Mapping[str, Any]) -> Mapping[str, Any]:
        self._renew_authority()
        binding = self._fault_cleanups.pop(step.campaign_hash, None)
        if binding is None:
            raise _CliError("fault_cleanup_binding_missing")
        payload = _fault_cleanup_body(
            step,
            self._lab.manifest,
            binding,
            evidence_hash=stable_hash({"step": step.to_dict(), "post": post_result}),
            policy_version=self._policy_version,
            created_at=self._target_time,
        )
        result = _request_loopback_json(
            self._target_url,
            "/faults/cleanup",
            method="POST",
            payload=payload,
            headers=self._fault_headers(),
            timeout_seconds=self._timeout_seconds,
        )
        evidence = result.get("evidence")
        if not isinstance(evidence, Mapping) or evidence.get("cleanup_mode") != "server_snapshot_restore":
            raise _CliError("fault_cleanup_snapshot_unproven")
        state = self._target_state()
        return {"status": "cleaned", "state": state, "state_hash": stable_hash(state), "receipt_hash": stable_hash(result)}

    def _target_state(self) -> dict[str, Any]:
        payload = _request_loopback_json(self._target_url, "/state", method="GET", timeout_seconds=self._timeout_seconds)
        return _collect_state(payload)

    def _fault_headers(self) -> dict[str, str]:
        return {
            "X-P174-Fault-Capability": self._fault_capability,
            "X-P174-Lease-Expires": self._lease_expires_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        }

    def _renew_authority(self) -> None:
        acquired_at = datetime.now(tz=UTC)
        self._lab.acquire_lease(self._owner_id, at=acquired_at)
        state_payload = _request_loopback_json(self._target_url, "/state", method="GET", timeout_seconds=self._timeout_seconds)
        observed_at = state_payload.get("observed_at")
        if not isinstance(observed_at, str):
            raise _CliError("target_observed_at_missing")
        try:
            target_time = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise _CliError("target_observed_at_invalid") from exc
        if target_time.tzinfo is None:
            raise _CliError("target_observed_at_timezone_required")
        lease_expires_at = target_time + timedelta(seconds=self._lab.manifest.lease_ttl_seconds)
        transport = self._lab.transport
        if not isinstance(transport, HttpP174ProviderTransport):
            raise _CliError("provider_transport_not_renewable")
        transport.renew_lease(lease_expires_at)
        self._lease_expires_at = lease_expires_at
        self._target_time = target_time.astimezone(UTC)


def build_parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(description="Run the deterministic P174 live-lab qualification harness.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--provider-manifest", type=Path)
    parser.add_argument("--observer-endpoint", required=True)
    parser.add_argument("--action-endpoint", required=True)
    parser.add_argument("--output-summary", required=True, type=Path)
    parser.add_argument("--output-jsonl", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument("--allow-live-lab", action="store_true")
    parser.add_argument("--authority-file", required=True, type=Path)
    parser.add_argument("--healthy-window-interval-seconds", type=float, default=_MIN_LIVE_WINDOW_INTERVAL_SECONDS)
    parser.add_argument("--owner-id", default="p175-live-harness")
    parser.add_argument("--max-scenarios", type=int, default=None)
    parser.add_argument("--diagnostic-campaign-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        summary = run_from_args(args)
    except (OSError, P174LiveHarnessError, _CliError, urllib.error.URLError) as exc:
        _emit({"ok": False, "status": "blocked", "error": str(exc), "error_type": type(exc).__name__}, stream=sys.stderr)
        return 2
    _emit(summary)
    return 0


def run_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.allow_live_lab is not True:
        raise _CliError("--allow-live-lab is required")
    if args.timeout_seconds <= 0 or args.timeout_seconds > 30:
        raise _CliError("--timeout-seconds must be between 0 and 30")
    if not math.isfinite(args.healthy_window_interval_seconds) or args.healthy_window_interval_seconds < _MIN_LIVE_WINDOW_INTERVAL_SECONDS:
        raise _CliError("--healthy-window-interval-seconds must be at least 15")
    if args.max_scenarios is not None and (args.max_scenarios <= 0 or args.max_scenarios > 100):
        raise _CliError("--max-scenarios must be between 1 and 100")
    if args.provider_manifest is None:
        raise _CliError("--provider-manifest is required")
    manifest = load_reviewed_manifest(args.manifest)
    provider_manifest = validate_manifest(json.loads(args.provider_manifest.read_text(encoding="utf-8")))
    authority = _load_authority_file(args.authority_file, provider_manifest)
    lease_expires_at = datetime.now(tz=UTC) + timedelta(seconds=provider_manifest.lease_ttl_seconds)
    transport = HttpP174ProviderTransport(
        base_url=_validate_private_or_loopback_base_url(args.action_endpoint, "action_endpoint"),
        capability=authority.action_capability,
        lease_expires_at=lease_expires_at,
        timeout_seconds=args.timeout_seconds,
        post_check_delay_seconds=1.0,
        post_check_samples=3,
    )
    lab = ProviderLab(provider_manifest, transport=transport)
    lab.acquire_lease(args.owner_id)
    recorder = JsonlEvidenceRecorder()
    summary = run_qualification(
        manifest,
        LoopbackObserverClient(
            args.observer_endpoint,
            timeout_seconds=args.timeout_seconds,
            min_interval_seconds=args.healthy_window_interval_seconds,
        ),
        ProviderLabActionClient(
            target_url=args.action_endpoint,
            lab=lab,
            owner_id=args.owner_id,
            fault_capability=authority.fault_capability,
            policy_version=authority.policy_version,
            lease_expires_at=lease_expires_at,
            timeout_seconds=args.timeout_seconds,
        ),
        recorder=recorder,
        max_scenarios=args.max_scenarios,
        diagnostic_campaign_only=args.diagnostic_campaign_only,
    )
    _write_text_atomic(args.output_jsonl, recorder.to_jsonl())
    _write_text_atomic(args.output_summary, json.dumps(summary, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n")
    return summary


def _load_authority_file(path: Path, manifest: ProviderManifest) -> _Authority:
    try:
        path_stat = os.lstat(path)
    except OSError as exc:
        raise _CliError("authority_file_unreadable") from exc
    if stat.S_ISLNK(path_stat.st_mode):
        raise _CliError("authority_file_symlink_forbidden")
    if not stat.S_ISREG(path_stat.st_mode):
        raise _CliError("authority_file_regular_required")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise _CliError("authority_file_unreadable") from exc
    try:
        opened_stat = os.fstat(descriptor)
        if not stat.S_ISREG(opened_stat.st_mode):
            raise _CliError("authority_file_regular_required")
        if stat.S_IMODE(opened_stat.st_mode) != 0o600:
            raise _CliError("authority_file_mode_must_be_0600")
        if opened_stat.st_size > _AUTHORITY_FILE_MAX_BYTES:
            raise _CliError("authority_file_too_large")
        raw = os.read(descriptor, _AUTHORITY_FILE_MAX_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(raw) > _AUTHORITY_FILE_MAX_BYTES:
        raise _CliError("authority_file_too_large")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _CliError("authority_file_utf8_required") from exc

    values: dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line or "=" not in line:
            raise _CliError(f"authority_file_line_invalid:{line_number}")
        key, value = line.split("=", 1)
        if key not in _AUTHORITY_FIELDS:
            raise _CliError(f"authority_file_key_forbidden:{key}")
        if key in values:
            raise _CliError(f"authority_file_key_duplicate:{key}")
        if not value or value != value.strip() or "\x00" in value or len(value) > _CAPABILITY_MAX_LENGTH:
            raise _CliError(f"authority_file_value_invalid:{key}")
        values[key] = value
    missing = _AUTHORITY_FIELDS - values.keys()
    if missing:
        raise _CliError(f"authority_file_keys_missing:{','.join(sorted(missing))}")

    action_capability = values["P174_ACTION_CAPABILITY"]
    fault_capability = values["P174_FAULT_CAPABILITY"]
    if not _CAPABILITY_MIN_LENGTH <= len(action_capability) <= _CAPABILITY_MAX_LENGTH:
        raise _CliError("authority_action_capability_length_invalid")
    if not _CAPABILITY_MIN_LENGTH <= len(fault_capability) <= _CAPABILITY_MAX_LENGTH:
        raise _CliError("authority_fault_capability_length_invalid")
    if action_capability == fault_capability:
        raise _CliError("authority_capabilities_must_be_distinct")

    expected_binding = {
        "P174_PROJECT_ID": manifest.project_id,
        "P174_TARGET_ID": manifest.target_id,
        "P174_RUN_ID": manifest.run_id,
        "P174_POLICY_VERSION": _POLICY_VERSION,
    }
    for key, expected in expected_binding.items():
        if values[key] != expected:
            raise _CliError(f"authority_binding_mismatch:{key}")
    return _Authority(
        action_capability=action_capability,
        fault_capability=fault_capability,
        project_id=values["P174_PROJECT_ID"],
        target_id=values["P174_TARGET_ID"],
        run_id=values["P174_RUN_ID"],
        policy_version=values["P174_POLICY_VERSION"],
    )


def _validate_loopback_base_url(raw: str, name: str) -> str:
    parsed = urlsplit(raw.rstrip("/"))
    if parsed.scheme != "http" or not parsed.hostname:
        raise _CliError(f"{name}_must_be_http_loopback")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise _CliError(f"{name}_must_not_include_auth_query_or_fragment")
    if parsed.path not in {"", "/"}:
        raise _CliError(f"{name}_path_forbidden")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise _CliError(f"{name}_host_must_be_loopback")
    if parsed.port is None or parsed.port <= 0 or parsed.port > 65535:
        raise _CliError(f"{name}_port_required")
    return raw.rstrip("/")


def _validate_private_or_loopback_base_url(raw: str, name: str) -> str:
    parsed = urlsplit(raw.rstrip("/"))
    if parsed.scheme != "http" or not parsed.hostname:
        raise _CliError(f"{name}_must_be_http_loopback_or_p174_private")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise _CliError(f"{name}_must_not_include_auth_query_or_fragment")
    if parsed.path not in {"", "/"}:
        raise _CliError(f"{name}_path_forbidden")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1", "10.174.0.10"}:
        raise _CliError(f"{name}_host_must_be_loopback_or_10_174")
    if parsed.port is None or parsed.port <= 0 or parsed.port > 65535:
        raise _CliError(f"{name}_port_required")
    return raw.rstrip("/")


def _request_loopback_json(
    base_url: str,
    path: str,
    *,
    method: str,
    timeout_seconds: float,
    payload: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    request = urllib.request.Request(
        base_url + path,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json", **dict(headers or {})},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        expected_status = 200 if method == "GET" else 202
        if response.status != expected_status:
            raise _CliError(f"loopback_http_status:{response.status}")
        raw = response.read(256 * 1024)
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise _CliError("loopback_response_object_required")
    return value


def _collect_healthy(payload: Mapping[str, Any]) -> bool:
    evaluation = payload.get("evaluation")
    if isinstance(evaluation, Mapping) and isinstance(evaluation.get("healthy"), bool):
        return bool(evaluation["healthy"])
    return payload.get("healthy") is True or payload.get("status") == "healthy"


def _collect_state(payload: Mapping[str, Any]) -> dict[str, Any]:
    state = payload.get("state")
    if isinstance(state, Mapping):
        result = dict(state)
        metrics = payload.get("metrics")
        if isinstance(metrics, Mapping):
            result.update(metrics)
        return result
    metrics = payload.get("metrics")
    if isinstance(metrics, Mapping):
        return dict(metrics)
    evaluation = payload.get("evaluation")
    if isinstance(evaluation, Mapping):
        return dict(evaluation)
    return dict(payload)


def _fault_body(
    step: ScenarioStep,
    manifest: Any,
    *,
    baseline_state: Mapping[str, Any],
    evidence_hash: str,
    policy_version: str,
    created_at: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": "p174.faults.v1",
        "request_id": _scenario_request_key("fault", step),
        "idempotency_key": _scenario_request_key("fault", step),
        "project_id": manifest.project_id,
        "target_id": step.target,
        "run_id": manifest.run_id,
        "fault": step.scenario.fault,
        "parameters": _fault_parameters(step, baseline_state),
        "created_at": created_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "evidence_hash": evidence_hash,
        "policy_version": policy_version,
    }


def _fault_parameters(step: ScenarioStep, baseline_state: Mapping[str, Any]) -> dict[str, Any]:
    if step.scenario.fault == "queue_backlog":
        pool_size = baseline_state.get("pool_size")
        if isinstance(pool_size, bool) or not isinstance(pool_size, int | float) or not math.isfinite(float(pool_size)):
            raise _CliError("fault_baseline_pool_size_invalid")
        numeric_pool_size = float(pool_size)
        if not numeric_pool_size.is_integer() or not 1 <= numeric_pool_size <= 64:
            raise _CliError("fault_baseline_pool_size_invalid")
        return {"items": max(12, int(numeric_pool_size) * 4)}
    if step.scenario.fault == "canary_regression":
        return {"version": "regressed"}
    if step.scenario.fault == "worker_pause":
        return {"pause_seconds": 30}
    return {}


def _runtime_cleanup_proven(baseline_state: Mapping[str, Any], cleanup_result: Mapping[str, Any]) -> bool:
    cleanup_state = cleanup_result.get("state")
    if not isinstance(cleanup_state, Mapping):
        return False
    return all(
        key in baseline_state and key in cleanup_state and cleanup_state[key] == baseline_state[key]
        for key in _PROTECTED_RUNTIME_STATE_FIELDS
    )


def _action_parameters(step: ScenarioStep, before_state: Mapping[str, Any]) -> dict[str, Any]:
    if step.scenario.action == "restart_worker":
        return {"pause_seconds": 0}
    if step.scenario.action == "rollback_canary":
        return {"version": "stable"}
    if step.scenario.action == "tune_pool":
        current = int(float(before_state.get("pool_size", 5)))
        return {"pool_size": current + 1 if current < 64 else current - 1}
    return {}


def _fault_cleanup_body(
    step: ScenarioStep,
    manifest: Any,
    binding: Mapping[str, str],
    *,
    evidence_hash: str,
    policy_version: str,
    created_at: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": "p174.faults.cleanup.v1",
        "request_id": _scenario_request_key("cleanup", step),
        "idempotency_key": _scenario_request_key("cleanup", step),
        "project_id": manifest.project_id,
        "target_id": step.target,
        "run_id": manifest.run_id,
        "original_request_id": binding["original_request_id"],
        "original_idempotency_key": binding["original_idempotency_key"],
        "cleanup_token": binding["cleanup_token"],
        "created_at": created_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "evidence_hash": evidence_hash,
        "policy_version": policy_version,
    }


def _scenario_request_key(kind: str, step: ScenarioStep) -> str:
    campaign_digest = step.campaign_hash.removeprefix("sha256:")
    if len(campaign_digest) != 64 or any(character not in "0123456789abcdef" for character in campaign_digest):
        raise _CliError("scenario_campaign_hash_invalid")
    return f"p175-{kind}-{campaign_digest}-{step.index}-{step.scenario.name}"


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _emit(value: Mapping[str, Any], *, stream: Any = None) -> None:
    output = stream or sys.stdout
    output.write(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n")
    output.flush()


if __name__ == "__main__":
    raise SystemExit(main())
