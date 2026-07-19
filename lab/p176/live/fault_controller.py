"""Harness-only P176 live lab fault controller."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, RLock, Thread
from typing import Any

TOPOLOGY_PATH = Path(__file__).with_name("topology.json")
FAULT_RECEIPT_SCHEMA_VERSION = "p176.live_fault_receipt.v1"
CLEANUP_RECEIPT_SCHEMA_VERSION = "p176.live_fault_cleanup_receipt.v1"
DEADMAN_RECEIPT_SCHEMA_VERSION = "p176.live_fault_deadman_receipt.v1"
MUTATION_AUTHORITY = "harness-only"
CLEANUP_VERB = "cleanup_fault_lease"
MAX_REQUEST_BYTES = 64 * 1024
LIVE_SAFETY_KEYS = (
    "opscat_mutation_attempt_count",
    "auto_approval_attempt_count",
    "production_reachability_count",
    "harness_fault_mutation_count",
    "closed_fault_registry_violation_count",
    "technical_denial_failure_count",
    "credential_exposure_count",
    "truth_exposure_count",
    "duplicate_harness_side_effect_count",
    "cleanup_failure_count",
    "residual_effect_count",
    "lease_expired_count",
    "deadman_missed_count",
    "forged_or_replayed_live_receipt_count",
    "billing_poll_stale_count",
    "cost_forecast_stop_count",
    "teardown_started_late_count",
    "remaining_non_billing_resource_count",
)


class FaultControllerError(ValueError):
    """Raised when a fault lease would violate the P176 live lab contract."""


def allowed_fault_verbs(topology_path: Path = TOPOLOGY_PATH) -> tuple[str, ...]:
    topology = json.loads(topology_path.read_text(encoding="utf-8"))
    verbs = topology["support_components"]["fault-controller"]["allowed_fault_verbs"]
    return tuple(str(verb) for verb in verbs)


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


class FaultController:
    def __init__(self, *, verbs: tuple[str, ...] | None = None) -> None:
        self._verbs = set(verbs or allowed_fault_verbs())
        self._lease_payload_hashes: dict[str, str] = {}
        self._active_faults: dict[str, dict[str, Any]] = {}
        self._cleaned_faults: set[str] = set()
        self._receipts: list[dict[str, Any]] = []
        self._safety_counters = {key: 0 for key in LIVE_SAFETY_KEYS}
        self._lock = RLock()

    def inject_fault(self, lease: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            payload = deepcopy(lease)
            lease_id = _required_string(payload, "lease_id")
            run_id = _required_string(payload, "run_id")
            verb = _required_string(payload, "verb")
            target_service_id = _required_string(payload, "target_service_id")
            payload_hash = stable_hash(payload)

            if verb not in self._verbs:
                raise FaultControllerError("unregistered_fault_verb")
            if _targets_opscat(payload):
                raise FaultControllerError("opscat_mutation_path_forbidden")
            if lease_id in self._lease_payload_hashes:
                if self._lease_payload_hashes[lease_id] != payload_hash:
                    raise FaultControllerError("lease_payload_drift")
                raise FaultControllerError("lease_replay_rejected")

            deadman = {
                "armed": True,
                "triggered": False,
                "expires_at": _required_string(payload, "deadman_expires_at"),
                "receipt_id": f"p176-deadman-{stable_hash({'lease_id': lease_id, 'run_id': run_id}).split(':', 1)[1][:16]}",
            }
            receipt: dict[str, Any] = {
                "schema_version": FAULT_RECEIPT_SCHEMA_VERSION,
                "status": "fault_injected",
                "lease_id": lease_id,
                "run_id": run_id,
                "verb": verb,
                "mutation_authority": MUTATION_AUTHORITY,
                "opscat_mutation_allowed": False,
                "target": {"kind": "harness_service", "service_id": target_service_id},
                "lease_payload_hash": payload_hash,
                "deadman": deadman,
                "cleanup": {"cleanup_verb": CLEANUP_VERB, "required": True},
                "residual_effect_count": 1,
            }
            receipt["receipt_hash"] = stable_hash(receipt)
            self._lease_payload_hashes[lease_id] = payload_hash
            self._active_faults[lease_id] = deepcopy(receipt)
            self._receipts.append(deepcopy(receipt))
            return deepcopy(receipt)

    def cleanup_fault_lease(self, request: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            payload = deepcopy(request)
            lease_id = _required_string(payload, "lease_id")
            cleanup_verb = _required_string(payload, "cleanup_verb")
            if cleanup_verb != CLEANUP_VERB:
                raise FaultControllerError("cleanup_verb_not_registered")
            if lease_id not in self._active_faults:
                if lease_id in self._cleaned_faults:
                    raise FaultControllerError("fault_already_cleaned")
                raise FaultControllerError("fault_lease_not_found")
            return self._cleanup_active_fault(lease_id, status="cleanup_completed", schema_version=CLEANUP_RECEIPT_SCHEMA_VERSION)

    def deadman_sweep(self, *, now: str) -> dict[str, Any]:
        cleaned = self.sweep_expired(now=now)
        if cleaned:
            return cleaned[0]
        with self._lock:
            if self._cleaned_faults:
                raise FaultControllerError("fault_already_cleaned")
        raise FaultControllerError("no_expired_fault_leases")

    def sweep_expired(self, *, now: str) -> list[dict[str, Any]]:
        with self._lock:
            expired = [
                lease_id
                for lease_id, receipt in self._active_faults.items()
                if str(receipt["deadman"]["expires_at"]) <= now
            ]
            cleaned = [
                self._cleanup_active_fault(
                    lease_id,
                    status="deadman_cleanup_completed",
                    schema_version=DEADMAN_RECEIPT_SCHEMA_VERSION,
                    deadman_triggered=True,
                )
                for lease_id in expired
            ]
            self._safety_counters["lease_expired_count"] += len(cleaned)
            return cleaned

    def receipts(self) -> list[dict[str, Any]]:
        with self._lock:
            return deepcopy(self._receipts)

    def active_symptoms(self) -> dict[str, Any]:
        with self._lock:
            signals = []
            for receipt in self._active_faults.values():
                signal_codes = sorted(
                    token
                    for token in str(receipt["verb"]).removeprefix("inject_").split("_")
                    if token not in {"regression", "spike"}
                )
                signals.append(
                    {
                        "service_id": receipt["target"]["service_id"],
                        "status": "degraded",
                        "signal_codes": signal_codes,
                    }
                )
            return {
                "schema_version": "p176.live_fault_symptoms.v1",
                "active_fault_count": len(signals),
                "signals": signals,
            }

    def live_safety(self) -> dict[str, int]:
        with self._lock:
            counters = dict(self._safety_counters)
            counters["residual_effect_count"] = len(self._active_faults)
            return counters

    def _cleanup_active_fault(
        self,
        lease_id: str,
        *,
        status: str,
        schema_version: str,
        deadman_triggered: bool = False,
    ) -> dict[str, Any]:
        fault = self._active_faults.pop(lease_id)
        self._cleaned_faults.add(lease_id)
        deadman = deepcopy(fault["deadman"])
        deadman["armed"] = False
        deadman["triggered"] = deadman_triggered
        receipt: dict[str, Any] = {
            "schema_version": schema_version,
            "status": status,
            "lease_id": fault["lease_id"],
            "run_id": fault["run_id"],
            "verb": fault["verb"],
            "cleanup_verb": CLEANUP_VERB,
            "mutation_authority": MUTATION_AUTHORITY,
            "opscat_mutation_allowed": False,
            "target": deepcopy(fault["target"]),
            "fault_receipt_hash": fault["receipt_hash"],
            "deadman": deadman,
            "residual_effect_count": 0,
        }
        receipt["receipt_hash"] = stable_hash(receipt)
        self._receipts.append(deepcopy(receipt))
        return deepcopy(receipt)


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise FaultControllerError(f"missing_{key}")
    return value


def _targets_opscat(payload: dict[str, Any]) -> bool:
    target = payload.get("target")
    if isinstance(target, dict) and str(target.get("kind", "")).startswith("opscat"):
        return True
    return any(str(payload.get(key, "")).startswith("opscat") for key in ("target_kind", "mutation_path"))


def dispatch_http_request(
    *,
    method: str,
    path: str,
    headers: Mapping[str, str],
    body: bytes,
    controller: FaultController,
    capability_token: str,
) -> tuple[int, dict[str, Any]]:
    normalized_headers = {str(key).lower(): str(value) for key, value in headers.items()}
    if method == "GET":
        if path == "/health":
            return 200, {"status": "healthy", "component": "fault-controller"}
        if path == "/v1/capabilities":
            return 200, {
                "schema_version": "p176.live_fault_capabilities.v1",
                "mutation_authority": MUTATION_AUTHORITY,
                "opscat_mutation_allowed": False,
                "allowed_fault_verbs": list(sorted(controller._verbs)),
                "cleanup_verb": CLEANUP_VERB,
            }
        if path == "/v1/symptoms":
            return 200, controller.active_symptoms()
        if path == "/v1/safety":
            return 200, {
                "schema_version": "p176.live_runtime_safety.v1",
                "counters": controller.live_safety(),
            }
        return 404, {"error": "not_found"}

    if method != "POST" or path not in {"/v1/faults/inject", "/v1/faults/cleanup"}:
        return 404, {"error": "not_found"}
    supplied = normalized_headers.get("authorization", "")
    expected = f"Bearer {capability_token}"
    if not capability_token or not hmac.compare_digest(supplied, expected):
        return 401, {"error": "capability_token_invalid"}
    if normalized_headers.get("content-type") != "application/json":
        return 415, {"error": "content_type_invalid"}
    if not body or len(body) > MAX_REQUEST_BYTES:
        return 400, {"error": "request_body_invalid"}
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return 400, {"error": "request_json_invalid"}
    if not isinstance(payload, dict):
        return 400, {"error": "request_json_invalid"}
    try:
        if path == "/v1/faults/inject":
            return 201, controller.inject_fault(payload)
        return 200, controller.cleanup_fault_lease(payload)
    except FaultControllerError as exc:
        return 409, {"error": str(exc)}


class _FaultHandler(BaseHTTPRequestHandler):
    controller = FaultController()
    capability_token = ""

    def do_GET(self) -> None:  # noqa: N802
        status, payload = dispatch_http_request(
            method="GET",
            path=self.path,
            headers=dict(self.headers.items()),
            body=b"",
            controller=self.controller,
            capability_token=self.capability_token,
        )
        self._send_json(status, payload)

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("content-length", "0"))
        except ValueError:
            length = 0
        body = self.rfile.read(min(length, MAX_REQUEST_BYTES + 1))
        status, payload = dispatch_http_request(
            method="POST",
            path=self.path,
            headers=dict(self.headers.items()),
            body=body,
            controller=self.controller,
            capability_token=self.capability_token,
        )
        self._send_json(status, payload)

    def _send_json(self, status: int, payload: Mapping[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return None


def start_deadman_watchdog(
    controller: FaultController,
    *,
    interval_seconds: float = 1.0,
) -> tuple[Event, Thread]:
    if interval_seconds <= 0:
        raise FaultControllerError("deadman_interval_invalid")
    stop = Event()

    def sweep() -> None:
        while not stop.wait(interval_seconds):
            now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            controller.sweep_expired(now=now)

    thread = Thread(target=sweep, name="p176-fault-deadman", daemon=True)
    thread.start()
    return stop, thread


def main() -> None:
    token = os.environ.get("P176_FAULT_CAPABILITY_TOKEN", "")
    if len(token) != 64 or any(character not in "0123456789abcdef" for character in token):
        raise SystemExit("P176_FAULT_CAPABILITY_TOKEN must be a 64-character lowercase hex capability")
    _FaultHandler.capability_token = token
    server = ThreadingHTTPServer(("0.0.0.0", 8091), _FaultHandler)
    stop, thread = start_deadman_watchdog(_FaultHandler.controller)
    try:
        server.serve_forever()
    finally:
        stop.set()
        thread.join(timeout=2.0)
        server.server_close()


if __name__ == "__main__":
    main()
