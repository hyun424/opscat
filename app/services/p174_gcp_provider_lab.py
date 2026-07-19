"""Typed, local-only P174 GCP provider-adapter contract lab.

The lab models the live provider boundary without granting network, shell, URL,
or real GCP mutation authority.  A fake in-memory transport is the only
transport implemented here.
"""

from __future__ import annotations

import json
import math
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from statistics import median
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

from app.services.p110_evaluation import stable_hash

MANIFEST_SCHEMA_VERSION = "p174.live_session_manifest.v1"
ACTION_SCHEMA_VERSION = "p174.provider_action_request.v1"
RECEIPT_SCHEMA_VERSION = "p174.provider_receipt.v1"
ALLOWED_ACTIONS: frozenset[str] = frozenset({"tune_pool", "restart_worker", "rollback_canary"})
ROLLBACK_ACTION = "rollback_canary"
OutcomeStatus = Literal["healthy", "harmful", "uncertain"]

_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_UNSAFE_VALUE_RE = re.compile(
    r"(?:https?://|wss?://|://|\$\{|`|;|&&|\|\||\b(?:bash|curl|delete|dns|endpoint|gcloud|host|kubectl|metadata|password|prod|production|rm\s+-rf|secret|shell|ssh|terraform|token|url|wget)\b)",
    re.IGNORECASE,
)
_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "organization_id",
        "billing_account_id",
        "project_id",
        "target_id",
        "run_id",
        "zone",
        "allowed_actions",
        "allowed_targets",
        "forbidden_project_ids",
        "lease_ttl_seconds",
        "deadman_seconds",
        "kill_switch",
        "dry_run",
        "production_mutation_allowed",
        "user_staging_mutation_allowed",
        "service_account_keys_allowed",
        "live_apply_acknowledged",
    }
)


class P174ProviderLabError(ValueError):
    """Raised when P174 provider-adapter safety boundaries cannot be proven."""


@dataclass(frozen=True)
class ProviderManifest:
    schema_version: str
    manifest_hash: str
    organization_id: str
    billing_account_id: str
    project_id: str
    target_id: str
    run_id: str
    zone: str
    allowed_actions: tuple[str, ...]
    allowed_targets: tuple[str, ...]
    forbidden_project_ids: tuple[str, ...]
    lease_ttl_seconds: int
    deadman_seconds: int
    kill_switch: bool
    dry_run: bool
    production_mutation_allowed: bool
    user_staging_mutation_allowed: bool
    service_account_keys_allowed: bool
    live_apply_acknowledged: bool


@dataclass(frozen=True)
class ProviderActionRequest:
    schema_version: str
    request_id: str
    idempotency_key: str
    project_id: str
    target_id: str
    run_id: str
    action: str
    parameters: Mapping[str, Any]
    evidence_hash: str
    policy_version: str
    created_at: datetime


@dataclass(frozen=True)
class Lease:
    owner_id: str
    acquired_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class TransportResult:
    status: OutcomeStatus
    metrics: Mapping[str, float]
    provider_claimed_success: bool
    evidence: Mapping[str, Any]


class ProviderTransport(Protocol):
    """Narrow transport boundary used by the policy/receipt state machine."""

    name: str

    def read(self, manifest: ProviderManifest) -> Mapping[str, Any]: ...

    def preflight(self, request: ProviderActionRequest) -> TransportResult: ...

    def execute(self, request: ProviderActionRequest) -> TransportResult: ...

    def post_check(self, request: ProviderActionRequest) -> TransportResult: ...

    def rollback(self, request: ProviderActionRequest) -> TransportResult: ...

    def verify_rollback(self, request: ProviderActionRequest) -> TransportResult: ...


class FakeGcpProviderTransport:
    """In-memory transport that records intended calls and mutates no provider."""

    name = "fake-gcp-in-memory"

    def __init__(
        self,
        *,
        before_metrics: Mapping[str, float] | None = None,
        after_metrics: Mapping[str, float] | None = None,
        post_check_status: OutcomeStatus = "healthy",
        rollback_check_status: OutcomeStatus = "healthy",
        provider_claimed_success: bool = True,
    ) -> None:
        self.before_metrics = dict(before_metrics or {"error_rate": 0.08, "latency_ms": 250.0, "pool_size": 5.0, "queue_depth": 20.0, "service_up": 1.0})
        self.after_metrics = dict(after_metrics or {"error_rate": 0.04, "latency_ms": 225.0, "pool_size": 8.0, "queue_depth": 16.0, "service_up": 1.0})
        self.post_check_status = post_check_status
        self.rollback_check_status = rollback_check_status
        self.provider_claimed_success = provider_claimed_success
        self.action_log: list[str] = []

    def read(self, manifest: ProviderManifest) -> Mapping[str, Any]:
        return {
            "transport": self.name,
            "project_id": manifest.project_id,
            "target_id": manifest.target_id,
            "run_id": manifest.run_id,
            "metrics": dict(self.before_metrics),
        }

    def preflight(self, request: ProviderActionRequest) -> TransportResult:
        self.action_log.append(f"preflight:{request.action}")
        return TransportResult("healthy", self.before_metrics, True, {"preflight": "accepted"})

    def execute(self, request: ProviderActionRequest) -> TransportResult:
        self.action_log.append(f"execute:{request.action}")
        return TransportResult("healthy", self.after_metrics, self.provider_claimed_success, {"execute": "simulated"})

    def post_check(self, request: ProviderActionRequest) -> TransportResult:
        self.action_log.append(f"post_check:{request.action}")
        status = "uncertain" if self.post_check_status == "healthy" and self.after_metrics == self.before_metrics else self.post_check_status
        return TransportResult(status, self.after_metrics, self.provider_claimed_success, {"post_check": status})

    def rollback(self, request: ProviderActionRequest) -> TransportResult:
        self.action_log.append(f"rollback:{request.action}")
        return TransportResult("healthy", self.before_metrics, True, {"rollback": ROLLBACK_ACTION})

    def verify_rollback(self, request: ProviderActionRequest) -> TransportResult:
        self.action_log.append(f"rollback_check:{request.action}")
        return TransportResult(self.rollback_check_status, self.before_metrics, True, {"rollback_check": self.rollback_check_status})


class HttpP174ProviderTransport:
    """Real transport for the isolated P174 target's typed action gateway.

    The endpoint is operator configuration, never model output. Only a private
    or loopback HTTP host and the fixed `/state`, `/actions`, and
    `/actions/rollback` paths are addressable.
    """

    name = "p174-private-http-v1"

    def __init__(
        self,
        *,
        base_url: str,
        capability: str,
        lease_expires_at: datetime,
        timeout_seconds: float = 5.0,
        post_check_delay_seconds: float = 2.0,
        post_check_samples: int = 3,
    ) -> None:
        parsed = urlsplit(base_url.rstrip("/"))
        if parsed.scheme != "http" or not parsed.hostname or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise P174ProviderLabError("action_endpoint_invalid")
        if parsed.path not in {"", "/"}:
            raise P174ProviderLabError("action_endpoint_path_forbidden")
        if parsed.hostname not in {"127.0.0.1", "10.174.0.10", "localhost"}:
            raise P174ProviderLabError("action_endpoint_host_forbidden")
        if len(capability) < 32:
            raise P174ProviderLabError("action_capability_invalid")
        self.base_url = base_url.rstrip("/")
        self._capability = capability
        self._lease_expires_at = _utc(lease_expires_at)
        self._timeout_seconds = timeout_seconds
        self._post_check_delay_seconds = post_check_delay_seconds
        if post_check_samples < 1:
            raise P174ProviderLabError("post_check_samples_invalid")
        self._post_check_samples = post_check_samples
        self._before: dict[str, dict[str, float]] = {}
        self._before_state: dict[str, dict[str, Any]] = {}

    def renew_lease(self, lease_expires_at: datetime) -> None:
        """Replace the short-lived runtime lease without changing capability scope."""

        self._lease_expires_at = _utc(lease_expires_at)

    def read(self, manifest: ProviderManifest) -> Mapping[str, Any]:
        payload = self._request("GET", "/state")
        _require_runtime_binding(payload, manifest.project_id, manifest.target_id, manifest.run_id)
        return payload

    def preflight(self, request: ProviderActionRequest) -> TransportResult:
        payload = self._request("GET", "/state")
        _require_runtime_binding(payload, request.project_id, request.target_id, request.run_id)
        metrics = _runtime_metrics(payload)
        self._before[request.request_id] = metrics
        self._before_state[request.request_id] = _runtime_state(payload)
        return TransportResult("healthy", metrics, True, _runtime_evidence(payload, phase="preflight"))

    def execute(self, request: ProviderActionRequest) -> TransportResult:
        payload = self._request("POST", "/actions", body=_runtime_request_body(request))
        _require_runtime_binding(payload, request.project_id, request.target_id, request.run_id)
        accepted = payload.get("accepted") is True
        if not accepted:
            raise P174ProviderLabError(f"runtime_action_rejected:{payload.get('reason', 'unknown')}")
        return TransportResult("healthy", _runtime_metrics(payload), True, _runtime_evidence(payload, phase="execute"))

    def post_check(self, request: ProviderActionRequest) -> TransportResult:
        payload: dict[str, Any] = {}
        samples: list[dict[str, float]] = []
        states: list[dict[str, Any]] = []
        for _ in range(self._post_check_samples):
            if self._post_check_delay_seconds > 0:
                time.sleep(self._post_check_delay_seconds)
            payload = self._request("GET", "/state")
            _require_runtime_binding(payload, request.project_id, request.target_id, request.run_id)
            samples.append(_runtime_metrics(payload))
            states.append(_runtime_state(payload))
        after = _representative_metrics(samples)
        before = self._before.get(request.request_id)
        before_state = self._before_state.get(request.request_id)
        status: OutcomeStatus = "uncertain"
        if before is not None and before_state is not None:
            score = score_outcome(before, after, provider_claimed_success=True)
            service_up = after.get("service_up", 0.0) >= 1.0
            score_value = float(score["score"])
            if not service_up or score_value < 0:
                status = "harmful"
            elif _action_recovery_proven(request, before, after, score) and _durability_proven(request, before, samples, before_state, states):
                status = "healthy"
        return TransportResult(status, after, True, _runtime_evidence(payload, phase="post_check"))

    def rollback(self, request: ProviderActionRequest) -> TransportResult:
        payload = self._request("POST", "/actions/rollback", body=_runtime_rollback_body(request))
        _require_runtime_binding(payload, request.project_id, request.target_id, request.run_id)
        accepted = payload.get("accepted") is True
        if not accepted:
            raise P174ProviderLabError(f"runtime_rollback_rejected:{payload.get('reason', 'unknown')}")
        return TransportResult("healthy", _runtime_metrics(payload), True, _runtime_evidence(payload, phase="rollback"))

    def verify_rollback(self, request: ProviderActionRequest) -> TransportResult:
        expected = self._before_state.get(request.request_id)
        if expected is None:
            return TransportResult("uncertain", {}, False, {"phase": "rollback_check", "reason": "preflight_state_missing"})
        payload: dict[str, Any] = {}
        samples: list[dict[str, float]] = []
        states: list[dict[str, Any]] = []
        for _ in range(self._post_check_samples):
            if self._post_check_delay_seconds > 0:
                time.sleep(self._post_check_delay_seconds)
            payload = self._request("GET", "/state")
            _require_runtime_binding(payload, request.project_id, request.target_id, request.run_id)
            samples.append(_runtime_metrics(payload))
            states.append(_runtime_state(payload))
        proven = _rollback_closure_proven(request, expected, samples, states)
        return TransportResult("healthy" if proven else "uncertain", samples[-1], False, _runtime_evidence(payload, phase="rollback_check"))

    def _request(self, method: str, path: str, *, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        encoded = None if body is None else json.dumps(dict(body), sort_keys=True, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=encoded,
            method=method,
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "x-p174-capability": self._capability,
                "x-p174-lease-expires": _iso(self._lease_expires_at),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                expected_status = 200 if method == "GET" else 202 if method == "POST" else None
                if expected_status is None or response.status != expected_status:
                    raise P174ProviderLabError(
                        f"runtime_http_status_mismatch:{method}:{response.status}:expected:{expected_status}"
                    )
                raw = response.read(65_537)
                if len(raw) > 65_536:
                    raise P174ProviderLabError("runtime_response_too_large")
        except urllib.error.HTTPError as exc:
            error_body = exc.read(4_096)
            try:
                error_payload = json.loads(error_body)
                reason = str(error_payload.get("reason", "rejected")) if isinstance(error_payload, dict) else "rejected"
            except json.JSONDecodeError:
                reason = "rejected"
            raise P174ProviderLabError(f"runtime_http_{exc.code}:{reason}") from exc
        except (OSError, urllib.error.URLError) as exc:
            raise P174ProviderLabError("runtime_transport_failed") from exc
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise P174ProviderLabError("runtime_response_invalid") from exc
        if not isinstance(value, dict):
            raise P174ProviderLabError("runtime_response_invalid")
        return value


class ProviderLab:
    def __init__(
        self,
        manifest: ProviderManifest,
        *,
        transport: ProviderTransport,
        now: Callable[[], datetime] | None = None,
        prior_receipts: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        self.manifest = manifest
        self.transport = transport
        self._now = now or (lambda: datetime.now(tz=UTC))
        self._receipts = [deepcopy(dict(receipt)) for receipt in prior_receipts]
        self._idempotency: dict[str, tuple[str, dict[str, Any]]] = {}
        self._lease: Lease | None = None
        self.validate_receipts()

    @property
    def receipts(self) -> tuple[dict[str, Any], ...]:
        """Return an immutable snapshot so callers cannot rewrite audit history."""

        return tuple(deepcopy(self._receipts))

    def acquire_lease(self, owner_id: str, *, at: datetime | None = None) -> dict[str, Any]:
        _require_id(owner_id, "owner_id")
        acquired_at = _utc(at or self._now())
        expires_at = acquired_at + timedelta(seconds=self.manifest.lease_ttl_seconds)
        self._lease = Lease(owner_id=owner_id, acquired_at=acquired_at, expires_at=expires_at)
        return {"owner_id": owner_id, "acquired_at": _iso(acquired_at), "expires_at": _iso(expires_at)}

    def read_state(self, owner_id: str) -> dict[str, Any]:
        now = self._require_live_authority(owner_id)
        state = dict(self.transport.read(self.manifest))
        receipt = self._receipt(
            {
                "receipt_type": "read",
                "owner_id": owner_id,
                "project_id": self.manifest.project_id,
                "target_id": self.manifest.target_id,
                "run_id": self.manifest.run_id,
                "observed_at": _iso(now),
                "state_hash": stable_hash(state),
                "transport": self.transport.name,
            }
        )
        self._append_receipt(receipt)
        return deepcopy(receipt)

    def run_action(self, owner_id: str, request: ProviderActionRequest) -> dict[str, Any]:
        now = self._require_live_authority(owner_id)
        normalized_request = _normalize_request(request, self.manifest)
        request_hash = stable_hash(normalized_request)
        prior = self._idempotency.get(request.idempotency_key)
        if prior is not None:
            prior_hash, prior_receipt = prior
            if prior_hash != request_hash:
                raise P174ProviderLabError("idempotency_conflict")
            return deepcopy(prior_receipt)

        state_sequence: list[str] = ["dry_run"]
        before_metrics: dict[str, float] = {}
        after_metrics: dict[str, float] = {}
        provider_claimed_success = False
        status = "dry_run_complete"
        rollback_reason: str | None = None
        failure_reason: str | None = None
        failure_detail: str | None = None

        try:
            preflight = self.transport.preflight(request)
            state_sequence.append("preflight")
            before_metrics = _metric_map(preflight.metrics)
            after_metrics = dict(before_metrics)
            provider_claimed_success = preflight.provider_claimed_success
        except Exception as exc:  # noqa: BLE001 - transport failures must become durable receipts
            state_sequence.append("preflight_failed")
            status = "blocked"
            failure_reason = f"preflight:{type(exc).__name__}"
            failure_detail = _exception_detail(exc)

        if status != "blocked" and not self.manifest.dry_run:
            try:
                self.transport.execute(request)
                state_sequence.append("execute")
                post_check = self.transport.post_check(request)
                state_sequence.append("post_check")
                after_metrics = _metric_map(post_check.metrics)
                provider_claimed_success = post_check.provider_claimed_success
                if post_check.status in {"harmful", "uncertain"}:
                    rollback_reason = "harmful_post_check" if post_check.status == "harmful" else "uncertain_post_check"
                    if request.action == "restart_worker":
                        status = "failed_closed"
                        failure_reason = f"{rollback_reason}:irreversible_action"
                    else:
                        self.transport.rollback(request)
                        state_sequence.append("rollback")
                        rollback_check = self.transport.verify_rollback(request)
                        state_sequence.append("rollback_check")
                        if rollback_check.status == "healthy":
                            status = "rolled_back"
                        else:
                            state_sequence.append("rollback_failed")
                            status = "rollback_failed"
                            failure_reason = "rollback:closure_not_proven"
                else:
                    status = "applied"
            except Exception as exc:  # noqa: BLE001 - preserve a receipt even after uncertain mutation
                failed_phase = "post_check" if "execute" in state_sequence else "execute"
                state_sequence.append(f"{failed_phase}_failed")
                failure_reason = f"{failed_phase}:{type(exc).__name__}"
                failure_detail = _exception_detail(exc)
                rollback_reason = f"{failed_phase}_failed"
                if request.action == "restart_worker":
                    status = "failed_closed"
                    failure_reason = f"{failure_reason};rollback:irreversible_action"
                else:
                    try:
                        self.transport.rollback(request)
                        state_sequence.append("rollback")
                        rollback_check = self.transport.verify_rollback(request)
                        state_sequence.append("rollback_check")
                        if rollback_check.status == "healthy":
                            status = "rolled_back"
                        else:
                            state_sequence.append("rollback_failed")
                            status = "rollback_failed"
                            failure_reason = f"{failure_reason};rollback:closure_not_proven"
                    except Exception as rollback_exc:  # noqa: BLE001 - rollback failure is the most important durable outcome
                        state_sequence.append("rollback_failed")
                        status = "rollback_failed"
                        failure_reason = f"{failure_reason};rollback:{type(rollback_exc).__name__}"
                        failure_detail = _exception_detail(rollback_exc)

        outcome_score = score_outcome(before_metrics, after_metrics, provider_claimed_success=provider_claimed_success)
        receipt_body: dict[str, Any] = {
            "receipt_type": "action",
            "owner_id": owner_id,
            "request_id": request.request_id,
            "idempotency_key": request.idempotency_key,
            "request_hash": request_hash,
            "manifest_hash": self.manifest.manifest_hash,
            "project_id": request.project_id,
            "target_id": request.target_id,
            "run_id": request.run_id,
            "action": request.action,
            "evidence_hash": request.evidence_hash,
            "policy_version": request.policy_version,
            "status": status,
            "state_sequence": state_sequence,
            "rollback_reason": rollback_reason,
            "failure_reason": failure_reason,
            "failure_detail": failure_detail,
            "irreversible_action": request.action == "restart_worker",
            "rollback_closure_claimed": status == "rolled_back" and request.action in {"tune_pool", "rollback_canary"},
            "outcome_score": outcome_score,
            "transport": self.transport.name,
            "observed_at": _iso(now),
        }
        receipt = self._receipt(receipt_body)
        self._append_receipt(receipt)
        stored = deepcopy(receipt)
        self._idempotency[request.idempotency_key] = (request_hash, stored)
        return deepcopy(stored)

    def validate_receipts(self) -> None:
        validate_receipt_chain(self._receipts, manifest_hash=self.manifest.manifest_hash)

    def _receipt(self, body: Mapping[str, Any]) -> dict[str, Any]:
        receipt = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "manifest_hash": self.manifest.manifest_hash,
            "previous_receipt_hash": None if not self._receipts else self._receipts[-1]["receipt_hash"],
            **dict(body),
        }
        receipt["receipt_hash"] = stable_hash(receipt)
        return receipt

    def _append_receipt(self, receipt: dict[str, Any]) -> None:
        self._receipts.append(receipt)
        self.validate_receipts()

    def _require_live_authority(self, owner_id: str) -> datetime:
        now = _utc(self._now())
        if self.manifest.kill_switch:
            raise P174ProviderLabError("kill_switch_active")
        if self._lease is None or self._lease.owner_id != owner_id:
            raise P174ProviderLabError("lease_missing")
        if now > self._lease.expires_at:
            raise P174ProviderLabError("lease_expired")
        if now > self._lease.acquired_at + timedelta(seconds=self.manifest.deadman_seconds):
            raise P174ProviderLabError("deadman_expired")
        return now


def validate_receipt_chain(receipts: Sequence[Mapping[str, Any]], *, manifest_hash: str) -> None:
    """Validate a receipt export independently of the live in-memory object."""

    previous_hash: str | None = None
    seen_hashes: set[str] = set()
    for receipt in receipts:
        if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
            raise P174ProviderLabError("receipt_schema_invalid")
        if receipt.get("manifest_hash") != manifest_hash:
            raise P174ProviderLabError("receipt_manifest_binding_invalid")
        if receipt.get("previous_receipt_hash") != previous_hash:
            raise P174ProviderLabError("receipt_chain_invalid")
        receipt_hash = str(receipt.get("receipt_hash", ""))
        if receipt_hash in seen_hashes:
            raise P174ProviderLabError("receipt_hash_duplicate")
        if receipt_hash != stable_hash({key: value for key, value in receipt.items() if key != "receipt_hash"}):
            raise P174ProviderLabError("receipt_hash_invalid")
        seen_hashes.add(receipt_hash)
        previous_hash = receipt_hash


def validate_manifest(raw: Mapping[str, Any]) -> ProviderManifest:
    unknown = set(raw) - _MANIFEST_FIELDS
    if unknown:
        raise P174ProviderLabError(f"invalid_manifest_fields:{sorted(unknown)}")
    if raw.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise P174ProviderLabError("manifest_schema_invalid")
    if set(_string_sequence(raw.get("allowed_actions"), "allowed_actions")) != ALLOWED_ACTIONS:
        raise P174ProviderLabError("allowed_actions_not_exact")

    allowed_targets = _string_sequence(raw.get("allowed_targets"), "allowed_targets")
    forbidden_project_ids = _string_sequence(raw.get("forbidden_project_ids"), "forbidden_project_ids")
    project_id = _string(raw.get("project_id"), "project_id")
    target_id = _string(raw.get("target_id"), "target_id")
    checked_strings: list[str] = [
        _string(raw.get("organization_id"), "organization_id"),
        _string(raw.get("billing_account_id"), "billing_account_id"),
        project_id,
        target_id,
        _string(raw.get("run_id"), "run_id"),
        _string(raw.get("zone"), "zone"),
        *allowed_targets,
        *forbidden_project_ids,
    ]
    for item in checked_strings:
        _require_safe_value(item, "manifest_value")
    if project_id in forbidden_project_ids:
        raise P174ProviderLabError("forbidden_project_selected")
    if target_id not in allowed_targets:
        raise P174ProviderLabError("target_not_allowed")
    run_id = _string(raw.get("run_id"), "run_id")
    for manifest_id in (project_id, target_id, run_id):
        _require_id(manifest_id, "manifest_id")

    if any(_bool(raw.get(key), key) for key in ("production_mutation_allowed", "user_staging_mutation_allowed", "service_account_keys_allowed", "live_apply_acknowledged")):
        raise P174ProviderLabError("live_authority_flag_enabled")

    lease_ttl_seconds = _positive_int(raw.get("lease_ttl_seconds"), "lease_ttl_seconds")
    deadman_seconds = _positive_int(raw.get("deadman_seconds"), "deadman_seconds")

    manifest_hash = stable_hash(dict(raw))
    return ProviderManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        manifest_hash=manifest_hash,
        organization_id=str(raw["organization_id"]),
        billing_account_id=str(raw["billing_account_id"]),
        project_id=project_id,
        target_id=target_id,
        run_id=run_id,
        zone=str(raw["zone"]),
        allowed_actions=tuple(sorted(ALLOWED_ACTIONS)),
        allowed_targets=tuple(allowed_targets),
        forbidden_project_ids=tuple(forbidden_project_ids),
        lease_ttl_seconds=lease_ttl_seconds,
        deadman_seconds=deadman_seconds,
        kill_switch=_bool(raw.get("kill_switch"), "kill_switch"),
        dry_run=_bool(raw.get("dry_run"), "dry_run"),
        production_mutation_allowed=False,
        user_staging_mutation_allowed=False,
        service_account_keys_allowed=False,
        live_apply_acknowledged=False,
    )


def score_outcome(before_metrics: Mapping[str, float], after_metrics: Mapping[str, float], *, provider_claimed_success: bool) -> dict[str, Any]:
    before_error = float(before_metrics.get("error_rate", 0.0))
    after_error = float(after_metrics.get("error_rate", before_error))
    before_latency = float(before_metrics.get("latency_ms", 0.0))
    after_latency = float(after_metrics.get("latency_ms", before_latency))
    error_delta = before_error - after_error
    latency_delta = before_latency - after_latency
    score = round(error_delta * 100.0 + latency_delta / 1000.0, 6)
    return {
        "score": score,
        "error_rate_delta": round(error_delta, 6),
        "latency_ms_delta": round(latency_delta, 6),
        "provider_claimed_success": provider_claimed_success,
        "scored_from_provider_claim": False,
        "outcome": "improved" if score > 0 else "not_improved",
    }


def _normalize_request(request: ProviderActionRequest, manifest: ProviderManifest) -> dict[str, Any]:
    if request.schema_version != ACTION_SCHEMA_VERSION:
        raise P174ProviderLabError("action_schema_invalid")
    for value, field in (
        (request.request_id, "request_id"),
        (request.idempotency_key, "idempotency_key"),
        (request.project_id, "project_id"),
        (request.target_id, "target_id"),
        (request.run_id, "run_id"),
        (request.policy_version, "policy_version"),
    ):
        _require_id(value, field)
        _require_safe_value(value, field)
    if request.project_id != manifest.project_id:
        raise P174ProviderLabError("project_binding_mismatch")
    if request.target_id != manifest.target_id or request.target_id not in manifest.allowed_targets:
        raise P174ProviderLabError("target_not_allowed")
    if request.run_id != manifest.run_id:
        raise P174ProviderLabError("run_binding_mismatch")
    if request.action not in ALLOWED_ACTIONS:
        raise P174ProviderLabError("action_not_allowed")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", request.evidence_hash):
        raise P174ProviderLabError("evidence_hash_invalid")
    parameters = _safe_parameters(request.parameters)
    return {
        "schema_version": request.schema_version,
        "request_id": request.request_id,
        "idempotency_key": request.idempotency_key,
        "project_id": request.project_id,
        "target_id": request.target_id,
        "run_id": request.run_id,
        "action": request.action,
        "parameters": parameters,
        "evidence_hash": request.evidence_hash,
        "policy_version": request.policy_version,
        "created_at": _iso(_utc(request.created_at)),
    }


def _runtime_request_body(request: ProviderActionRequest) -> dict[str, Any]:
    return {
        "schema_version": "p174.actions.v1",
        "request_id": request.request_id,
        "idempotency_key": request.idempotency_key,
        "project_id": request.project_id,
        "target_id": request.target_id,
        "run_id": request.run_id,
        "action": request.action,
        "parameters": _safe_parameters(request.parameters),
        "evidence_hash": request.evidence_hash,
        "policy_version": request.policy_version,
        "created_at": _iso(_utc(request.created_at)),
    }


def _runtime_rollback_body(request: ProviderActionRequest) -> dict[str, Any]:
    return {
        "schema_version": "p174.actions.rollback.v1",
        "request_id": request.request_id + "-rollback",
        "idempotency_key": request.idempotency_key + "-rollback",
        "project_id": request.project_id,
        "target_id": request.target_id,
        "run_id": request.run_id,
        "original_request_id": request.request_id,
        "original_idempotency_key": request.idempotency_key,
        "created_at": _iso(_utc(request.created_at)),
        "evidence_hash": request.evidence_hash,
        "policy_version": request.policy_version,
    }


def _require_runtime_binding(payload: Mapping[str, Any], project_id: str, target_id: str, run_id: str) -> None:
    binding = payload.get("state", payload)
    if not isinstance(binding, Mapping):
        raise P174ProviderLabError("runtime_binding_missing")
    if binding.get("project_id") != project_id:
        raise P174ProviderLabError("runtime_project_binding_mismatch")
    if binding.get("target_id") != target_id:
        raise P174ProviderLabError("runtime_target_binding_mismatch")
    if binding.get("run_id") != run_id:
        raise P174ProviderLabError("runtime_run_binding_mismatch")


def _runtime_metrics(payload: Mapping[str, Any]) -> dict[str, float]:
    value = payload.get("metrics", payload.get("after_metrics"))
    if not isinstance(value, Mapping):
        raise P174ProviderLabError("runtime_metrics_missing")
    result: dict[str, float] = {}
    for key, item in value.items():
        if not isinstance(key, str) or isinstance(item, bool) or not isinstance(item, int | float):
            raise P174ProviderLabError("runtime_metrics_invalid")
        numeric = float(item)
        if not math.isfinite(numeric):
            raise P174ProviderLabError("runtime_metrics_invalid")
        result[key] = numeric
    required = {"error_rate", "latency_ms", "service_up", "pool_size", "queue_depth"}
    if not required <= set(result):
        raise P174ProviderLabError("runtime_metrics_incomplete")
    if not 0.0 <= result["error_rate"] <= 1.0:
        raise P174ProviderLabError("runtime_metrics_invalid")
    if result["latency_ms"] < 0.0:
        raise P174ProviderLabError("runtime_metrics_invalid")
    if result["service_up"] not in {0.0, 1.0}:
        raise P174ProviderLabError("runtime_metrics_invalid")
    if result["pool_size"] <= 0.0 or not result["pool_size"].is_integer():
        raise P174ProviderLabError("runtime_metrics_invalid")
    if result["queue_depth"] < 0.0 or not result["queue_depth"].is_integer():
        raise P174ProviderLabError("runtime_metrics_invalid")
    return result


def _runtime_state(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = payload.get("state", payload)
    if not isinstance(value, Mapping):
        raise P174ProviderLabError("runtime_state_missing")
    result = {str(key): item for key, item in value.items()}
    metrics = payload.get("metrics")
    if isinstance(metrics, Mapping):
        for key in ("pool_size", "queue_depth"):
            if key in metrics:
                result.setdefault(key, metrics[key])
    observed_at = payload.get("observed_at")
    if isinstance(observed_at, str):
        result["observed_at"] = observed_at
    return result


def _representative_metrics(samples: Sequence[Mapping[str, float]]) -> dict[str, float]:
    if not samples:
        raise P174ProviderLabError("runtime_metric_samples_missing")
    keys = set(samples[0])
    if any(set(sample) != keys for sample in samples):
        raise P174ProviderLabError("runtime_metric_shape_changed")
    return {key: float(median(sample[key] for sample in samples)) for key in sorted(keys)}


def _runtime_evidence(payload: Mapping[str, Any], *, phase: str) -> dict[str, Any]:
    return {
        "phase": phase,
        "state_hash": stable_hash(dict(payload)),
        "status": str(payload.get("status", "observed")),
    }


def _action_recovery_proven(
    request: ProviderActionRequest,
    before: Mapping[str, float],
    after: Mapping[str, float],
    score: Mapping[str, Any],
) -> bool:
    score_value = float(score["score"])
    if score_value <= 0:
        return False
    error_improvement = float(score["error_rate_delta"]) >= 0.01
    latency_improvement = float(score["latency_ms_delta"]) >= max(5.0, before.get("latency_ms", 0.0) * 0.05)
    if request.action == "tune_pool":
        return after.get("pool_size", 0.0) > before.get("pool_size", 0.0) and after.get("queue_depth", 0.0) < before.get("queue_depth", 0.0) and (error_improvement or latency_improvement)
    if request.action == "restart_worker":
        return after.get("queue_depth", 0.0) < before.get("queue_depth", 0.0) * 0.9 and (error_improvement or latency_improvement)
    if request.action == "rollback_canary":
        return error_improvement or latency_improvement
    return False


def _durability_proven(
    request: ProviderActionRequest,
    before: Mapping[str, float],
    samples: Sequence[Mapping[str, float]],
    before_state: Mapping[str, Any],
    states: Sequence[Mapping[str, Any]],
) -> bool:
    if not samples or any(sample.get("service_up", 0.0) < 1.0 for sample in samples):
        return False
    if request.action == "tune_pool":
        queue_depths = [before.get("queue_depth", 0.0), *(sample.get("queue_depth", 0.0) for sample in samples)]
        return all(current <= previous for previous, current in pairwise(queue_depths)) and queue_depths[-1] < queue_depths[0]
    if request.action == "restart_worker":
        return _restart_worker_completion_proven(before, samples, before_state, states)
    if request.action == "rollback_canary":
        if len(states) != len(samples):
            return False
        metrics_recovered = all(
            sample.get("error_rate", 1.0) <= before.get("error_rate", 1.0) and sample.get("latency_ms", float("inf")) <= before.get("latency_ms", float("inf"))
            for sample in samples
        )
        canary_stable = all(state.get("canary_version") == "stable" for state in states)
        return metrics_recovered and canary_stable
    return False


def _restart_worker_completion_proven(
    before: Mapping[str, float],
    samples: Sequence[Mapping[str, float]],
    before_state: Mapping[str, Any],
    states: Sequence[Mapping[str, Any]],
) -> bool:
    if len(samples) < 3 or len(states) != len(samples):
        return False
    before_queue_depth = before.get("queue_depth", 0.0)
    queue_depths = [sample.get("queue_depth", 0.0) for sample in samples]
    recovered_samples = sum(queue_depth < before_queue_depth * 0.9 for queue_depth in queue_depths)
    if recovered_samples < len(samples) // 2 + 1:
        return False
    pool_sizes = [max(1.0, sample.get("pool_size", 1.0)) for sample in samples]
    if any(sample.get("queue_depth", float("inf")) > max(20.0, pool_size * 4.0) for sample, pool_size in zip(samples, pool_sizes, strict=True)):
        return False
    before_generation = before_state.get("worker_restart_generation")
    if not isinstance(before_generation, int) or isinstance(before_generation, bool):
        return False
    generations: list[int] = []
    for state in states:
        generation = state.get("worker_restart_generation")
        if not isinstance(generation, int) or isinstance(generation, bool):
            return False
        generations.append(generation)
    if any(generation != before_generation + 1 for generation in generations):
        return False
    before_jobs = before_state.get("worker_jobs_total")
    if not isinstance(before_jobs, int) or isinstance(before_jobs, bool):
        return False
    typed_worker_jobs: list[int] = []
    for state in states:
        value = state.get("worker_jobs_total")
        if not isinstance(value, int) or isinstance(value, bool):
            return False
        typed_worker_jobs.append(value)
    if not all(current >= previous for previous, current in pairwise([before_jobs, *typed_worker_jobs])) or typed_worker_jobs[-1] <= before_jobs:
        return False
    return all(_worker_pause_released(state) for state in states)


def _worker_pause_released(state: Mapping[str, Any]) -> bool:
    paused_until = state.get("worker_paused_until")
    if paused_until is None:
        return False
    if not isinstance(paused_until, str):
        return False
    try:
        pause_deadline = datetime.fromisoformat(paused_until.replace("Z", "+00:00"))
    except ValueError:
        return False
    observed_at = state.get("observed_at")
    if not isinstance(observed_at, str):
        return False
    try:
        reference_time = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    return _utc(pause_deadline) <= _utc(reference_time)


def _rollback_closure_proven(
    request: ProviderActionRequest,
    expected: Mapping[str, Any],
    samples: Sequence[Mapping[str, float]],
    states: Sequence[Mapping[str, Any]],
) -> bool:
    if not samples or len(samples) != len(states) or any(sample.get("service_up", 0.0) < 1.0 for sample in samples):
        return False
    if request.action == "tune_pool":
        return all(state.get("pool_size") == expected.get("pool_size") for state in states)
    if request.action == "rollback_canary":
        return all(state.get("canary_version") == expected.get("canary_version") for state in states)
    return False


def _safe_parameters(value: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        key_text = str(key)
        _require_id(key_text, "parameter_key")
        _require_safe_value(key_text, "parameter_key")
        if isinstance(item, str):
            _require_safe_value(item, key_text)
            result[key_text] = item
        elif isinstance(item, bool):
            result[key_text] = item
        elif isinstance(item, int | float) and not isinstance(item, bool):
            result[key_text] = item
        else:
            raise P174ProviderLabError("unsafe_parameter_value")
    return result


def _metric_map(value: Mapping[str, float]) -> dict[str, float]:
    return {str(key): float(item) for key, item in value.items()}


def _exception_detail(exc: Exception) -> str:
    """Keep a bounded single-line root cause without serializing internals."""

    detail = " ".join(str(exc).split())
    return detail[:256] or type(exc).__name__


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise P174ProviderLabError(f"{field}_invalid")
    return value


def _string_sequence(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str) or not value:
        raise P174ProviderLabError(f"{field}_invalid")
    return tuple(_string(item, field) for item in value)


def _bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise P174ProviderLabError(f"{field}_invalid")
    return value


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0 or value > 86_400:
        raise P174ProviderLabError(f"{field}_invalid")
    return value


def _require_id(value: str, field: str) -> None:
    if not _ID_RE.fullmatch(value):
        raise P174ProviderLabError(f"{field}_invalid")


def _require_safe_value(value: str, field: str) -> None:
    if _UNSAFE_VALUE_RE.search(value):
        raise P174ProviderLabError(f"unsafe_{field}")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return _utc(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = [
    "ACTION_SCHEMA_VERSION",
    "ALLOWED_ACTIONS",
    "MANIFEST_SCHEMA_VERSION",
    "P174ProviderLabError",
    "ProviderActionRequest",
    "ProviderLab",
    "ProviderManifest",
    "ProviderTransport",
    "FakeGcpProviderTransport",
    "HttpP174ProviderTransport",
    "score_outcome",
    "validate_receipt_chain",
    "validate_manifest",
]
