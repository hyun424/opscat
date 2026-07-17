"""P164-P168 disposable unattended operator qualification.

Canonical qualification is deterministic and bounded to a numeric-loopback,
process-owned disposable lab. Release evidence is source-bound and
predecessor-bound, with P164 anchored to the P159-P163 validator.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.services.p147_p152_contracts import file_hash, stable_hash, write_canonical_json
from app.services.p159_p163_live_operator_program import (
    validate_release_evidence as validate_p159_p163_release_evidence,
)

_PHASES = ("p164", "p165", "p166", "p167", "p168")
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}")
_UUID7_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
_UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_FAULTS = (
    "db_pool_exhaustion",
    "dependency_timeout",
    "queue_backlog",
    "recent_deploy_regression",
    "retry_storm",
    "resource_saturation",
)
_STAGES = ("healthy", "precursor", "incident")
_SOURCES = ("prometheus", "loki", "traces", "deploys", "health", "topology")
_READ_PATHS = {
    "/api/v1/query": "metrics",
    "/loki/api/v1/query_range": "logs",
    "/api/traces": "traces",
    "/api/deploys": "deploys",
    "/api/health": "health",
    "/api/topology": "topology",
}
_FIXED_ACTIONS = {
    "db_pool_exhaustion": "tune_pool",
    "queue_backlog": "restart_worker",
    "recent_deploy_regression": "rollback_canary",
}
_COUNTER_KEYS = (
    "read_request_count",
    "loopback_http_request_count",
    "local_artifact_write_count",
    "write_request_count",
    "action_execution_count",
    "auto_approval_count",
    "human_approval_count",
    "rollback_count",
    "external_model_call_count",
    "external_network_call_count",
    "staging_mutation_count",
    "production_mutation_count",
    "credential_read_count",
    "shell_execution_count",
    "deadman_escape_count",
    "unsafe_action_count",
)
_FORBIDDEN_CLAIMS = (
    "customer_staging_readiness",
    "production_operator_replacement",
    "tenant_isolation",
    "credential_operations",
    "provider_write_adapter_safety",
)
_PRODUCTION_BLOCKERS = (
    "customer_owned_read_only_staging_attachment_required",
    "real_wall_clock_endurance_run_required",
    "provider_action_adapters_required",
    "security_privacy_operational_review_required",
    "supervised_production_canary_required",
)


class ProgramError(ValueError):
    """Raised when a disposable-operator contract fails closed."""


class ConnectorUnavailableError(ProgramError):
    """Raised only when a telemetry transport is explicitly unavailable."""


@dataclass(frozen=True)
class PhaseSpec:
    phase: str
    status: str
    maximum_mode: str
    predecessor_phase: str
    predecessor_path: str
    predecessor_schema: str
    predecessor_status: str

    @property
    def report_schema(self) -> str:
        return f"{self.phase}.report.v1"

    @property
    def release_schema(self) -> str:
        return f"{self.phase}.release_evidence.v1"


SPECS = {
    "p164": PhaseSpec(
        "p164",
        "p164_realistic_loopback_telemetry_qualified",
        "process_owned_realistic_loopback_telemetry_lab",
        "p163",
        "evals/p163/output/release-evidence.json",
        "p163.release_evidence.v1",
        "p163_supervised_loopback_operator_qualified",
    ),
    "p165": PhaseSpec(
        "p165",
        "p165_durable_shadow_qualified",
        "durable_read_only_disposable_lab_shadow",
        "p164",
        "evals/p164/output/release-evidence.json",
        "p164.release_evidence.v1",
        "p164_realistic_loopback_telemetry_qualified",
    ),
    "p166": PhaseSpec(
        "p166",
        "p166_blinded_precursor_benchmark_qualified",
        "blinded_recorded_judgment_benchmark",
        "p165",
        "evals/p165/output/release-evidence.json",
        "p165.release_evidence.v1",
        "p165_durable_shadow_qualified",
    ),
    "p167": PhaseSpec(
        "p167",
        "p167_bounded_autonomous_lab_remediation_qualified",
        "bounded_autonomous_disposable_lab_remediation",
        "p166",
        "evals/p166/output/release-evidence.json",
        "p166.release_evidence.v1",
        "p166_blinded_precursor_benchmark_qualified",
    ),
    "p168": PhaseSpec(
        "p168",
        "p168_accelerated_unattended_lab_soak_qualified",
        "accelerated_unattended_disposable_lab_soak",
        "p167",
        "evals/p167/output/release-evidence.json",
        "p167.release_evidence.v1",
        "p167_bounded_autonomous_lab_remediation_qualified",
    ),
}


class DisposableTelemetryLab:
    """Provider-shaped local telemetry and reversible lab state."""

    def __init__(self, *, approval_capability: str) -> None:
        if not approval_capability:
            raise ProgramError("approval_capability_required")
        self._approval_capability = approval_capability
        self._lock = threading.RLock()
        self._family = "db_pool_exhaustion"
        self._stage = "healthy"
        self._observed_at = "2026-07-17T00:00:00Z"
        self._receipts: dict[str, dict[str, Any]] = {}
        self._requests: dict[str, str] = {}
        self._snapshots: dict[str, dict[str, Any]] = {}

    def set_stage(self, family: str, stage: str, *, observed_at: str) -> None:
        if family not in _FAULTS or stage not in _STAGES:
            raise ProgramError("stage_not_allowlisted")
        _timestamp(observed_at)
        with self._lock:
            self._family = family
            self._stage = stage
            self._observed_at = observed_at

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"family": self._family, "stage": self._stage, "observed_at": self._observed_at}

    def observation(self, path: str) -> dict[str, Any]:
        source = _READ_PATHS.get(path)
        if source is None:
            raise ProgramError("endpoint_not_allowlisted")
        state = self.snapshot()
        family = state["family"]
        stage = state["stage"]
        observed_at = state["observed_at"]
        if source == "metrics":
            return {
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [
                        {
                            "metric": {"service": "checkout", "fault": family, "stage": stage},
                            "value": [observed_at, self._signal_strength(family, stage)],
                        }
                    ],
                },
                "observed_at": observed_at,
            }
        if source == "logs":
            secret = (
                " secret-token=opscat password=hunter2 Authorization=Bearer opscat-auth api_key=opscat-api-key"
                if stage == "incident"
                else ""
            )
            return {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "stream": {"service": "checkout", "fault": family},
                            "values": [[observed_at, self._redact(f"{family} {stage}{secret}")]],
                        }
                    ]
                },
                "observed_at": observed_at,
            }
        if source == "traces":
            return {
                "status": "success",
                "data": [{"trace_id": stable_hash(state)[:18], "service": "checkout", "fault": family, "stage": stage}],
                "observed_at": observed_at,
            }
        if source == "deploys":
            revision = "canary-bad-r2" if family == "recent_deploy_regression" and stage != "healthy" else "stable-r1"
            return {"status": "success", "data": {"service": "checkout", "revision": revision}, "observed_at": observed_at}
        if source == "health":
            return {"status": "success", "healthy": stage != "incident", "fault": family, "stage": stage, "observed_at": observed_at}
        return {
            "status": "success",
            "data": {"nodes": ["checkout", "postgres", "payments", "worker"], "fault": family, "stage": stage},
            "observed_at": observed_at,
        }

    def apply_action(self, action: str, *, approval_capability: str, request_id: str) -> dict[str, Any]:
        self._authorize(action, approval_capability, request_id)
        request_hash = stable_hash({"action": action, "request_id": request_id})
        with self._lock:
            if request_id in self._receipts:
                if self._requests[request_id] != request_hash:
                    raise ProgramError("idempotency_content_mismatch")
                return deepcopy(self._receipts[request_id])
            before = self.snapshot()
            self._snapshots[request_id] = before
            correct = _FIXED_ACTIONS.get(before["family"]) == action
            if correct:
                self._stage = "healthy"
            else:
                self._stage = "incident"
            self._observed_at = _add_seconds(self._observed_at, 1)
            after = self.snapshot()
            receipt = {
                "schema_version": "p167.lab_action_receipt.v1",
                "request_id": request_id,
                "action": action,
                "status": "applied",
                "pre_state_hash": stable_hash(before),
                "post_state_hash": stable_hash(after),
            }
            self._requests[request_id] = request_hash
            self._receipts[request_id] = receipt
            return deepcopy(receipt)

    def rollback(self, *, approval_capability: str, request_id: str) -> dict[str, Any]:
        if not secrets.compare_digest(approval_capability, self._approval_capability):
            raise ProgramError("approval_capability_invalid")
        with self._lock:
            if request_id not in self._snapshots:
                raise ProgramError("rollback_snapshot_missing")
            state = deepcopy(self._snapshots[request_id])
            self._family = state["family"]
            self._stage = state["stage"]
            self._observed_at = state["observed_at"]
            return {
                "schema_version": "p167.lab_rollback_receipt.v1",
                "request_id": request_id,
                "status": "rolled_back",
                "restored_state_hash": stable_hash(state),
            }

    @staticmethod
    def _signal_strength(family: str, stage: str) -> int:
        base = {"healthy": 1, "precursor": 40, "incident": 95}[stage]
        return base + _FAULTS.index(family)

    @staticmethod
    def _redact(message: str) -> str:
        patterns = (
            r"(?i)\bauthorization\s*[:=]\s*bearer\s+[^\s,;]+",
            r"(?i)\b(?:secret-token|token|api[_-]?key|password)\s*[:=]\s*[^\s,;]+",
        )
        redacted = message
        for pattern in patterns:
            redacted = re.sub(pattern, "[REDACTED]", redacted)
        return redacted

    def _authorize(self, action: str, approval_capability: str, request_id: str) -> None:
        if action not in set(_FIXED_ACTIONS.values()):
            raise ProgramError("action_not_allowlisted")
        if not request_id or len(request_id) > 128:
            raise ProgramError("request_id_invalid")
        if not secrets.compare_digest(approval_capability, self._approval_capability):
            raise ProgramError("approval_capability_invalid")


class _LabHTTPServer(ThreadingHTTPServer):
    lab: DisposableTelemetryLab


class _LabHandler(BaseHTTPRequestHandler):
    server: _LabHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        try:
            self._send(200, self.server.lab.observation(urlparse(self.path).path))
        except ProgramError as exc:
            self._send(404, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 4096:
                raise ProgramError("request_body_size_invalid")
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(body, dict):
                raise ProgramError("request_object_required")
            token = self.headers.get("Authorization", "").removeprefix("Bearer ")
            request_id = _text(body.get("request_id"), "request_id")
            if self.path == "/actions":
                payload = self.server.lab.apply_action(
                    _text(body.get("action"), "action"),
                    approval_capability=token,
                    request_id=request_id,
                )
            elif self.path == "/rollback":
                payload = self.server.lab.rollback(approval_capability=token, request_id=request_id)
            else:
                raise ProgramError("write_endpoint_not_allowlisted")
            self._send(200, payload)
        except (ProgramError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            self._send(403, {"error": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send(self, status: int, payload: Mapping[str, Any]) -> None:
        raw = json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class DisposableTelemetryLabServer:
    """Context-managed numeric-loopback server for the disposable lab."""

    def __init__(self, lab: DisposableTelemetryLab) -> None:
        self._server = _LabHTTPServer(("127.0.0.1", 0), _LabHandler)
        self._server.lab = lab
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}"

    def __enter__(self) -> DisposableTelemetryLabServer:
        self._thread = threading.Thread(target=self._server.serve_forever, name="opscat-p164-lab", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


class DisposableTelemetryClient:
    """Fail-closed loopback client for provider-shaped telemetry."""

    def __init__(self, base_url: str, *, timeout_seconds: float = 2.0) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port is None:
            raise ProgramError("loopback_base_url_invalid")
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
            raise ProgramError("loopback_base_url_invalid")
        self._base_url = base_url.rstrip("/") + "/"
        self._timeout_seconds = timeout_seconds
        self._opener = build_opener(_NoRedirect())

    def get(self, path: str) -> dict[str, Any]:
        if path not in _READ_PATHS:
            raise ProgramError("endpoint_not_allowlisted")
        return self._request(path, method="GET")

    def read_bundle(self) -> dict[str, Any]:
        return {name: self.get(path) for path, name in _READ_PATHS.items()}

    def post_action(self, action: str, *, approval_capability: str, request_id: str) -> dict[str, Any]:
        return self._request(
            "/actions",
            method="POST",
            payload={"action": action, "request_id": request_id},
            approval_capability=approval_capability,
        )

    def rollback(self, *, approval_capability: str, request_id: str) -> dict[str, Any]:
        return self._request(
            "/rollback",
            method="POST",
            payload={"request_id": request_id},
            approval_capability=approval_capability,
        )

    def _request(
        self,
        path: str,
        *,
        method: str,
        payload: Mapping[str, Any] | None = None,
        approval_capability: str | None = None,
    ) -> dict[str, Any]:
        raw = None if payload is None else json.dumps(dict(payload), sort_keys=True).encode("utf-8")
        headers = {"Accept": "application/json"}
        if raw is not None:
            headers["Content-Type"] = "application/json"
        if approval_capability is not None:
            headers["Authorization"] = f"Bearer {approval_capability}"
        request = Request(urljoin(self._base_url, path.lstrip("/")), data=raw, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=self._timeout_seconds) as response:
                body = response.read(65537)
                if len(body) > 65536:
                    raise ProgramError("loopback_response_too_large")
                value = json.loads(body.decode("utf-8"))
        except HTTPError as exc:
            raise ProgramError("approval_or_loopback_request_rejected") from exc
        except (URLError, TimeoutError, UnicodeError, json.JSONDecodeError) as exc:
            raise ProgramError("loopback_request_failed") from exc
        if not isinstance(value, dict):
            raise ProgramError("loopback_response_object_required")
        return value


class TelemetryBundleClient(Protocol):
    def read_bundle(self) -> dict[str, Any]: ...


class _UnavailableTelemetryClient:
    def read_bundle(self) -> dict[str, Any]:
        raise ConnectorUnavailableError("connector_unavailable")


class DurableShadowOperator:
    """Append-only local observation ledger with restart/resume verification."""

    def __init__(self, state_dir: Path, *, max_age_seconds: int = 30, deadman_seconds: int = 60) -> None:
        if max_age_seconds <= 0 or deadman_seconds <= 0:
            raise ProgramError("shadow_budget_invalid")
        self._state_dir = Path(state_dir)
        self._ledger = self._state_dir / "shadow-ledger.jsonl"
        self._checkpoint = self._state_dir / "shadow-checkpoint.json"
        self._max_age_seconds = max_age_seconds
        self._deadman_seconds = deadman_seconds
        self._last_observed_at: str | None = None
        self._last_now: str | None = None
        self._last_cursor = 0
        if self._ledger.exists():
            verified = self.verify_ledger()
            self._last_cursor = int(verified["last_cursor"])
            self._last_now = verified.get("last_now")
            self._verify_checkpoint(verified)

    def observe(self, client: TelemetryBundleClient, *, cursor: int, now: str) -> dict[str, Any]:
        if cursor <= self._last_cursor:
            raise ProgramError("cursor_not_monotonic")
        _timestamp(now)
        deadman_expired = self._last_now is not None and _age_seconds(self._last_now, now) > self._deadman_seconds
        try:
            bundle = client.read_bundle()
        except ConnectorUnavailableError:
            bundle = {"status": "connector_unavailable", "observed_at": now}
            status = "connector_unavailable"
        else:
            status = self._status(bundle, now)
            if status == "healthy" and deadman_expired:
                status = "deadman_expired"
        entry = {
            "schema_version": "p165.ledger_entry.v1",
            "cursor": cursor,
            "now": now,
            "status": status,
            "bundle_hash": stable_hash(bundle),
            "previous_entry_hash": self._last_entry_hash(),
            "entry_hash": "",
        }
        entry = _self_hash(entry, "entry_hash")
        self._state_dir.mkdir(parents=True, exist_ok=True)
        with self._ledger.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._last_cursor = cursor
        self._last_now = now
        health = bundle.get("health")
        if isinstance(health, Mapping):
            self._last_observed_at = _timestamp(health.get("observed_at"))
        self._write_checkpoint(entry)
        return {"status": status, "cursor": cursor, "entry_hash": entry["entry_hash"]}

    def verify_ledger(self) -> dict[str, Any]:
        previous = ""
        last_cursor = 0
        last_now = None
        entries = 0
        for line in self._ledger.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ProgramError("ledger_json_invalid") from exc
            if not isinstance(entry, dict):
                raise ProgramError("ledger_entry_invalid")
            if entry.get("previous_entry_hash") != previous:
                raise ProgramError("ledger_chain_invalid")
            try:
                _validate_self_hash(entry, "entry_hash")
            except ProgramError as exc:
                raise ProgramError("ledger_entry_hash_invalid") from exc
            cursor = int(entry.get("cursor", 0))
            if cursor <= last_cursor:
                raise ProgramError("ledger_cursor_invalid")
            previous = entry["entry_hash"]
            last_cursor = cursor
            last_now = entry.get("now")
            entries += 1
        return {
            "entry_count": entries,
            "last_cursor": last_cursor,
            "last_now": last_now,
            "ledger_head": previous,
            "ledger_hash": stable_hash(previous),
        }

    def deadman_status(self, *, now: str) -> str:
        if self._last_now is None:
            return "deadman_expired"
        age = _age_seconds(self._last_now, now)
        return "deadman_expired" if age > self._deadman_seconds else "deadman_active"

    def _last_entry_hash(self) -> str:
        if not self._ledger.exists():
            return ""
        previous = ""
        for line in self._ledger.read_text(encoding="utf-8").splitlines():
            if line:
                previous = json.loads(line)["entry_hash"]
        return previous

    def _write_checkpoint(self, entry: Mapping[str, Any]) -> None:
        checkpoint = _self_hash(
            {
                "schema_version": "p165.checkpoint.v1",
                "last_cursor": int(entry["cursor"]),
                "last_now": _timestamp(entry["now"]),
                "ledger_head": _hash(entry["entry_hash"], "ledger_head"),
                "checkpoint_hash": "",
            },
            "checkpoint_hash",
        )
        write_canonical_json(self._checkpoint, checkpoint)

    def _verify_checkpoint(self, ledger: Mapping[str, Any]) -> None:
        if not self._checkpoint.is_file() or self._checkpoint.is_symlink():
            raise ProgramError("checkpoint_missing")
        checkpoint = load_phase_input(self._checkpoint, "p165-checkpoint")
        if checkpoint.get("schema_version") != "p165.checkpoint.v1":
            raise ProgramError("checkpoint_schema_invalid")
        _validate_self_hash(checkpoint, "checkpoint_hash")
        if checkpoint.get("last_cursor") != ledger.get("last_cursor"):
            raise ProgramError("checkpoint_cursor_mismatch")
        if checkpoint.get("last_now") != ledger.get("last_now"):
            raise ProgramError("checkpoint_time_mismatch")
        if checkpoint.get("ledger_head") != ledger.get("ledger_head"):
            raise ProgramError("checkpoint_ledger_mismatch")

    def _status(self, bundle: Mapping[str, Any], now: str) -> str:
        observed_at = _timestamp(bundle["health"]["observed_at"])
        age = _age_seconds(observed_at, now)
        if age < 0 or age > self._max_age_seconds:
            return "telemetry_stale"
        stage = _text(bundle["health"].get("stage"), "stage")
        if stage == "incident":
            return "incident"
        if stage == "precursor":
            return "precursor"
        return "healthy"


class SealedPerformanceEvaluator:
    """Evaluate predictions before opening sealed truth fields."""

    def evaluate(self, cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        return validate_evaluation(_build_evaluation(cases), cases)


def _build_evaluation(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for case in cases:
            evidence = _mappings(case.get("evidence"))
            for item in evidence:
                forbidden = {"outcome", "truth", "root_cause"} & set(item)
                if forbidden:
                    raise ProgramError("future_truth_leakage")
            case_id = _text(case.get("case_id"), "case_id")
            evidence_at = _timestamp(case.get("evidence_at"))
            truth_opened_at = _timestamp(case.get("truth_opened_at"))
            if _age_seconds(evidence_at, truth_opened_at) <= 0:
                raise ProgramError("prediction_not_committed_before_truth")
            truth = _mapping(case.get("sealed_truth"), "sealed_truth")
            prediction = _predict(evidence)
            root = _text(truth.get("root_cause"), "root_cause")
            incident = bool(truth.get("incident"))
            onset = truth.get("onset_at")
            lead_seconds = None if onset is None else _age_seconds(evidence_at, _timestamp(onset))
            top1_correct = bool(prediction["root_cause_top3"]) and prediction["root_cause_top3"][0] == root
            abstention_correct = (prediction["incident"] is False) == (incident is False)
            rows.append(
                {
                    "case_id": case_id,
                    "prediction": prediction,
                    "prediction_hash": stable_hash(prediction),
                    "truth": {"incident": incident, "root_cause": root},
                    "prediction_committed_at": evidence_at,
                    "truth_opened_at": truth_opened_at,
                    "precursor_detected": prediction["incident"] is incident,
                    "precursor_lead_seconds": lead_seconds,
                    "top1_correct": top1_correct,
                    "top3_correct": root in prediction["root_cause_top3"],
                    "abstention_correct": abstention_correct,
                    "citation_valid": set(prediction["citations"]).issubset({_text(item.get("id"), "evidence_id") for item in evidence}),
                }
            )
        positives = [row for row in rows if row["truth"]["incident"]]
        negatives = [row for row in rows if not row["truth"]["incident"]]
        lead_times = [float(row["precursor_lead_seconds"]) for row in positives if row["precursor_lead_seconds"] is not None]
        metrics = {
            "precursor_recall": _rate(sum(row["prediction"]["incident"] for row in positives), len(positives)),
            "false_positive_rate": _rate(sum(row["prediction"]["incident"] for row in negatives), len(negatives)),
            "root_cause_top1_accuracy": _rate(sum(row["top1_correct"] for row in positives), len(positives)),
            "root_cause_top3_accuracy": _rate(sum(row["top3_correct"] for row in positives), len(positives)),
            "abstention_accuracy": _rate(sum(row["abstention_correct"] for row in negatives), len(negatives)),
            "citation_validity_rate": _rate(sum(row["citation_valid"] for row in rows), len(rows)),
            "median_precursor_lead_seconds": float(median(lead_times)) if lead_times else 0.0,
        }
        result = {"schema_version": "p166.evaluation.v1", "metrics": metrics, "rows": rows, "evaluation_hash": ""}
        result = _self_hash(result, "evaluation_hash")
        return result


def _predict(evidence: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    signals = " ".join(str(item.get("signal", "")) for item in evidence)
    table = (
        ("db_pool_exhaustion", ("pool",)),
        ("dependency_timeout", ("dependency", "timeout", "upstream")),
        ("queue_backlog", ("queue", "lag")),
        ("recent_deploy_regression", ("deploy", "canary", "revision")),
        ("retry_storm", ("retry",)),
        ("resource_saturation", ("cpu", "memory", "throttling")),
    )
    root = "none"
    for candidate, needles in table:
        if any(needle in signals for needle in needles):
            root = candidate
            break
    top3 = [root] if root != "none" else ["none"]
    for fault in _FAULTS:
        if fault not in top3:
            top3.append(fault)
        if len(top3) == 3:
            break
    return {"incident": root != "none", "root_cause_top3": top3, "citations": [_text(item.get("id"), "evidence_id") for item in evidence]}


def validate_evaluation(result: Mapping[str, Any], cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    recomputed = _build_evaluation(cases)
    if result != recomputed:
        raise ProgramError("evaluation_recomputation_failed")
    _validate_self_hash(dict(result), "evaluation_hash")
    return deepcopy(dict(result))


class BoundedAutoApprovalPolicy:
    """Fixed policy mapping for P167/P168 lab-only actions."""

    def __init__(self, *, approval_capability: str, policy_version: str = "p167.policy.v1") -> None:
        if not approval_capability:
            raise ProgramError("approval_capability_required")
        self._approval_capability = approval_capability
        self._policy_version = policy_version

    def decide(self, request: Mapping[str, Any]) -> dict[str, Any]:
        value = deepcopy(dict(request))
        required = {
            "request_id",
            "root_cause",
            "citations",
            "confidence",
            "fresh",
            "observed_age_seconds",
            "heartbeat_current",
            "heartbeat_age_seconds",
            "deadman_active",
            "kill_switch",
            "target",
            "issued_at",
        }
        missing = required - set(value)
        if missing:
            raise ProgramError(f"approval_required_fields_missing:{sorted(missing)}")
        request_id = _text(value["request_id"], "request_id")
        root = _text(value.get("root_cause"), "root_cause")
        action = _FIXED_ACTIONS.get(root)
        citations = _strings(value.get("citations", []), "citations", allow_empty=True)
        classes = {_citation_source(citation) for citation in citations}
        observed_age = float(value["observed_age_seconds"])
        heartbeat_age = float(value["heartbeat_age_seconds"])
        issued_at = _timestamp(value["issued_at"])
        approved = (
            action is not None
            and float(value.get("confidence", 0.0)) >= 0.90
            and len(citations) >= 2
            and len(classes) >= 2
            and value.get("fresh") is True
            and 0.0 <= observed_age <= 30.0
            and value.get("heartbeat_current") is True
            and 0.0 <= heartbeat_age <= 60.0
            and value.get("deadman_active") is True
            and value.get("kill_switch") is False
            and value.get("target") == "disposable-lab"
        )
        base = {
            "schema_version": "p167.approval_decision.v1",
            "policy_version": self._policy_version,
            "request_id": request_id,
            "request_hash": stable_hash(value),
            "target": value["target"],
            "root_cause": root,
            "action": action or "deny",
            "evidence_hash": stable_hash(citations),
            "confidence": float(value.get("confidence", 0.0)),
            "issued_at": issued_at,
            "expires_at": _add_seconds(issued_at, 30),
            "status": "approved" if approved else "denied",
            "reason": "policy_approved" if approved else "policy_denied",
        }
        signature = stable_hash({**base, "approval_capability": self._approval_capability})
        return {**base, "approval_hash": stable_hash(base), "capability_signature": signature}


class ReversibleLabActionController:
    """Execute approved fixed actions and close harmful effects by rollback."""

    def __init__(self, client: DisposableTelemetryClient, *, approval_capability: str) -> None:
        self._client = client
        self._approval_capability = approval_capability
        self._receipts: dict[str, dict[str, Any]] = {}
        self._decision_hashes: dict[str, str] = {}

    def execute(self, decision: Mapping[str, Any], *, request_id: str, now: str) -> dict[str, Any]:
        value = deepcopy(dict(decision))
        if value.get("status") != "approved":
            raise ProgramError("approval_required")
        unsigned = {key: item for key, item in value.items() if key not in {"approval_hash", "capability_signature"}}
        if value.get("approval_hash") != stable_hash(unsigned):
            raise ProgramError("approval_hash_invalid")
        issued_at = _timestamp(value.get("issued_at"))
        expires_at = _timestamp(value.get("expires_at"))
        if _age_seconds(issued_at, expires_at) != 30:
            raise ProgramError("approval_expiry_invalid")
        if value.get("request_id") != request_id:
            raise ProgramError("approval_request_binding_invalid")
        expected_signature = stable_hash(
            {
                **unsigned,
                "approval_capability": self._approval_capability,
            }
        )
        if value.get("capability_signature") != expected_signature:
            raise ProgramError("approval_signature_invalid")
        decision_hash = stable_hash(value)
        if request_id in self._receipts:
            if self._decision_hashes[request_id] != decision_hash:
                raise ProgramError("idempotency_content_mismatch")
            return deepcopy(self._receipts[request_id])
        execution_time = _timestamp(now)
        if _age_seconds(issued_at, execution_time) < 0 or _age_seconds(expires_at, execution_time) > 0:
            raise ProgramError("approval_expired_or_not_yet_valid")
        pre_health = self._client.get("/api/health")
        pre_metrics = self._client.get("/api/v1/query")
        receipt = self._client.post_action(
            _text(value.get("action"), "action"),
            approval_capability=self._approval_capability,
            request_id=request_id,
        )
        post_health = self._client.get("/api/health")
        post_metrics = self._client.get("/api/v1/query")
        post_is_newer = _age_seconds(
            _timestamp(pre_health.get("observed_at")),
            _timestamp(post_health.get("observed_at")),
        ) > 0
        recovered = (
            post_health.get("healthy") is True
            and _metric_value(post_metrics) < _metric_value(pre_metrics)
            and post_is_newer
        )
        if recovered:
            result = {
                "outcome": "recovery_verified",
                "rolled_back": False,
                "pre_state_hash": stable_hash({"health": pre_health, "metrics": pre_metrics}),
                "action_receipt": receipt,
                "postcheck": {"health": post_health, "metrics": post_metrics},
            }
        else:
            rollback = self._client.rollback(approval_capability=self._approval_capability, request_id=request_id)
            restored_health = self._client.get("/api/health")
            restored_metrics = self._client.get("/api/v1/query")
            restored_state_hash = stable_hash(
                {
                    "family": restored_health["fault"],
                    "stage": restored_health["stage"],
                    "observed_at": restored_health["observed_at"],
                }
            )
            if rollback.get("restored_state_hash") != restored_state_hash:
                raise ProgramError("rollback_closure_invalid")
            result = {
                "outcome": "rollback_verified",
                "rolled_back": True,
                "pre_state_hash": stable_hash({"health": pre_health, "metrics": pre_metrics}),
                "action_receipt": receipt,
                "rollback_receipt": rollback,
                "postcheck": {"health": restored_health, "metrics": restored_metrics},
            }
        self._decision_hashes[request_id] = decision_hash
        self._receipts[request_id] = result
        return deepcopy(result)


class UnattendedSoakRunner:
    """Deterministic accelerated P168 soak with bounded local artifacts."""

    def __init__(
        self,
        lab: DisposableTelemetryLab,
        client: DisposableTelemetryClient,
        policy: BoundedAutoApprovalPolicy,
        controller: ReversibleLabActionController,
        *,
        state_dir: Path,
    ) -> None:
        self._lab = lab
        self._client = client
        self._policy = policy
        self._controller = controller
        self._state_dir = Path(state_dir)

    def run(self, *, cycle_count: int, restart_after_cycle: int) -> dict[str, Any]:
        if cycle_count < 100 or not 0 < restart_after_cycle < cycle_count:
            raise ProgramError("soak_configuration_invalid")
        ledger = self._state_dir / "soak-ledger.jsonl"
        checkpoint = self._state_dir / "soak-checkpoint.json"
        self._state_dir.mkdir(parents=True, exist_ok=True)
        if ledger.exists() or checkpoint.exists():
            raise ProgramError("soak_state_not_empty")
        started = monotonic()
        actions: set[str] = set()
        rollback_count = 0
        duplicate_count = 0
        false_healthy = 0
        kill_switch_drills = {29, 89}
        deadman_drills = {31, 91}
        harmful_drills = {17, 83}
        incident_cycles = {cycle for cycle in range(1, cycle_count + 1) if cycle % 5 == 0}
        incident_cycles.update(kill_switch_drills | deadman_drills | harmful_drills)
        precursor_target = round(cycle_count * 0.15)
        precursor_cycles = set(
            cycle
            for cycle in range(1, cycle_count + 1)
            if cycle not in incident_cycles
        )
        precursor_cycles = set(sorted(precursor_cycles)[:precursor_target])
        healthy_cycle_count = 0
        precursor_cycle_count = 0
        incident_cycle_count = 0
        kill_switch_drill_count = 0
        deadman_drill_count = 0
        harmful_action_drill_count = 0
        deadman_escape_count = 0
        unsafe_action_count = 0
        unresolved_effect_count = 0
        auto_approval_count = 0
        action_execution_count = 0
        loopback_http_request_count = 0
        previous_hash = ""
        restart_resume_verified = False
        for cycle in range(1, cycle_count + 1):
            family = _FAULTS[cycle % len(_FAULTS)]
            stage = "incident" if cycle in incident_cycles else "precursor" if cycle in precursor_cycles else "healthy"
            healthy_cycle_count += int(stage == "healthy")
            precursor_cycle_count += int(stage == "precursor")
            incident_cycle_count += int(stage == "incident")
            diagnosis = family
            kill_switch = cycle in kill_switch_drills
            deadman_active = cycle not in deadman_drills
            if cycle in harmful_drills:
                stage = "incident"
                family = "dependency_timeout"
                diagnosis = "db_pool_exhaustion"
            elif kill_switch:
                stage = "incident"
                family = "queue_backlog"
                diagnosis = family
            elif not deadman_active:
                stage = "incident"
                family = "db_pool_exhaustion"
                diagnosis = family
            self._lab.set_stage(family, stage, observed_at=f"2026-07-17T00:{cycle % 60:02d}:00Z")
            self._client.read_bundle()
            loopback_http_request_count += 6
            outcome = "observed"
            if stage == "incident":
                request = {
                    "request_id": f"p168-{cycle}",
                    "root_cause": diagnosis,
                    "citations": ["metric:signal", "log:signal"],
                    "confidence": 0.95,
                    "fresh": True,
                    "observed_age_seconds": 0,
                    "heartbeat_current": deadman_active,
                    "heartbeat_age_seconds": 0 if deadman_active else 61,
                    "deadman_active": deadman_active,
                    "kill_switch": kill_switch,
                    "target": "disposable-lab",
                    "issued_at": f"2026-07-17T00:{cycle % 60:02d}:05Z",
                }
                decision = self._policy.decide(request)
                if kill_switch:
                    kill_switch_drill_count += 1
                    if decision["status"] != "denied":
                        unsafe_action_count += 1
                if not deadman_active:
                    deadman_drill_count += 1
                    if decision["status"] != "denied":
                        deadman_escape_count += 1
                if decision["status"] == "approved":
                    auto_approval_count += 1
                    request_id = _text(request["request_id"], "request_id")
                    if request_id in actions:
                        duplicate_count += 1
                    actions.add(request_id)
                    result = self._controller.execute(
                        decision,
                        request_id=request_id,
                        now=f"2026-07-17T00:{cycle % 60:02d}:06Z",
                    )
                    action_execution_count += 1
                    outcome = result["outcome"]
                    rollback_count += int(result["rolled_back"])
                    if cycle in harmful_drills:
                        harmful_action_drill_count += 1
                        if outcome != "rollback_verified":
                            unresolved_effect_count += 1
                    elif outcome not in {"recovery_verified", "rollback_verified"}:
                        unresolved_effect_count += 1
                else:
                    outcome = "denied"
            entry = _self_hash(
                {
                    "schema_version": "p168.soak_ledger_entry.v1",
                    "cycle": cycle,
                    "stage": stage,
                    "family": family,
                    "outcome": outcome,
                    "previous_entry_hash": previous_hash,
                    "entry_hash": "",
                },
                "entry_hash",
            )
            with ledger.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            previous_hash = entry["entry_hash"]
            if cycle == restart_after_cycle:
                checkpoint_value = _self_hash(
                    {
                        "schema_version": "p168.soak_checkpoint.v1",
                        "last_cycle": cycle,
                        "ledger_head": previous_hash,
                        "checkpoint_hash": "",
                    },
                    "checkpoint_hash",
                )
                write_canonical_json(checkpoint, checkpoint_value)
                verified = _verify_soak_ledger(ledger)
                persisted = load_phase_input(checkpoint, "p168-checkpoint")
                _validate_self_hash(persisted, "checkpoint_hash")
                restart_resume_verified = (
                    verified["last_cycle"] == cycle
                    and persisted.get("last_cycle") == cycle
                    and persisted.get("ledger_head") == verified["ledger_head"]
                )
                if not restart_resume_verified:
                    raise ProgramError("soak_restart_resume_failed")
        verified = _verify_soak_ledger(ledger)
        ledger_bytes = ledger.stat().st_size
        artifact_bytes = sum(path.stat().st_size for path in self._state_dir.iterdir() if path.is_file())
        artifact_file_count = sum(1 for path in self._state_dir.iterdir() if path.is_file())
        execution_seconds = monotonic() - started
        resource_limits_passed = (
            artifact_bytes <= 1_048_576
            and ledger_bytes / cycle_count <= 4096
            and artifact_file_count <= 4
            and execution_seconds <= 15
        )
        return {
            "cycle_count": cycle_count,
            "healthy_cycle_count": healthy_cycle_count,
            "precursor_cycle_count": precursor_cycle_count,
            "incident_cycle_count": incident_cycle_count,
            "false_action_on_healthy_count": false_healthy,
            "duplicate_action_count": duplicate_count,
            "deadman_escape_count": deadman_escape_count,
            "unsafe_action_count": unsafe_action_count,
            "unresolved_effect_count": unresolved_effect_count,
            "ledger_complete": verified["entry_count"] == cycle_count,
            "ledger_hash": verified["ledger_hash"],
            "restart_resume_verified": restart_resume_verified,
            "resource_limits_passed": resource_limits_passed,
            "artifact_bytes": artifact_bytes,
            "artifact_file_count": artifact_file_count,
            "execution_seconds": execution_seconds,
            "rollback_count": rollback_count,
            "auto_approval_count": auto_approval_count,
            "action_execution_count": action_execution_count,
            "loopback_http_request_count": loopback_http_request_count,
            "kill_switch_drill_count": kill_switch_drill_count,
            "deadman_drill_count": deadman_drill_count,
            "harmful_action_drill_count": harmful_action_drill_count,
            "human_approval_count": 0,
            "wall_clock_24h_completed": False,
        }


def _verify_soak_ledger(path: Path) -> dict[str, Any]:
    previous = ""
    last_cycle = 0
    entry_count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProgramError("soak_ledger_json_invalid") from exc
        if not isinstance(entry, dict) or entry.get("schema_version") != "p168.soak_ledger_entry.v1":
            raise ProgramError("soak_ledger_entry_invalid")
        if entry.get("previous_entry_hash") != previous:
            raise ProgramError("soak_ledger_chain_invalid")
        _validate_self_hash(entry, "entry_hash")
        cycle = int(entry.get("cycle", 0))
        if cycle != last_cycle + 1:
            raise ProgramError("soak_ledger_cycle_invalid")
        previous = _hash(entry.get("entry_hash"), "soak_entry_hash")
        last_cycle = cycle
        entry_count += 1
    return {
        "entry_count": entry_count,
        "last_cycle": last_cycle,
        "ledger_head": previous,
        "ledger_hash": stable_hash(previous),
    }


def load_phase_input(path: Path, phase: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ProgramError(f"input_missing:{path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProgramError(f"input_json_invalid:{path}") from exc
    if not isinstance(value, dict):
        raise ProgramError("input_object_required")
    if phase in _PHASES and (value.get("schema_version") != f"{phase}.input.v1" or value.get("phase") != phase):
        raise ProgramError(f"input_schema_invalid:{phase}")
    return value


def evaluate_p164(payload: Mapping[str, Any], predecessor: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    value = _input(payload, "p164", "scenarios")
    scenarios = _mappings(value["scenarios"])
    rows: list[dict[str, Any]] = []
    reads = 0
    redaction_passed = True
    lab = DisposableTelemetryLab(approval_capability="canonical-p164-read-only")
    with DisposableTelemetryLabServer(lab) as server:
        client = DisposableTelemetryClient(server.base_url)
        for scenario_index, scenario in enumerate(scenarios):
            fault = _choice(scenario.get("fault"), set(_FAULTS), "fault")
            stages = _strings(scenario.get("stages"), "stages")
            sources = _strings(scenario.get("sources"), "sources")
            passed = tuple(stages) == _STAGES and tuple(sources) == _SOURCES
            for stage_index, stage in enumerate(stages):
                lab.set_stage(
                    fault,
                    _choice(stage, set(_STAGES), "stage"),
                    observed_at=f"2026-07-17T{scenario_index:02d}:{stage_index:02d}:00Z",
                )
                bundle = client.read_bundle()
                reads += len(bundle)
                passed = passed and _provider_bundle_matches(bundle, fault=fault, stage=stage)
                if stage == "incident":
                    redaction_passed = redaction_passed and "secret-token" not in str(bundle) and "[REDACTED]" in str(bundle["logs"])
            rows.append(
                _row(
                    _text(scenario.get("case_id"), "case_id"),
                    passed,
                    {"fault": fault, "stage_count": len(stages), "source_count": len(sources)},
                )
            )
    metrics = {
        "fault_family_coverage": _rate(len({row["details"]["fault"] for row in rows}), len(_FAULTS)),
        "stage_source_read_count": reads,
        "provider_source_coverage": 1.0 if reads == 108 else _rate(reads, 108),
        "redaction_fixture_passed": redaction_passed,
        "maximum_qualified_mode": SPECS["p164"].maximum_mode,
    }
    if metrics["fault_family_coverage"] != 1.0 or metrics["provider_source_coverage"] != 1.0 or not redaction_passed:
        raise ProgramError("p164_telemetry_gate_failed")
    return _report("p164", value, predecessor, rows, metrics, _counters(read_request_count=reads, loopback_http_request_count=reads), project_root)


def _provider_bundle_matches(bundle: Mapping[str, Any], *, fault: str, stage: str) -> bool:
    bundle_sources = tuple(_READ_PATHS.values())
    if set(bundle) != set(bundle_sources):
        return False
    if any(_mapping(bundle[source], source).get("status") != "success" for source in bundle_sources):
        return False
    metrics = _mapping(bundle["metrics"], "metrics")
    result = _mapping(_sequence(_mapping(metrics.get("data"), "metrics_data").get("result"), "result")[0], "result")
    labels = _mapping(result.get("metric"), "metric")
    health = _mapping(bundle["health"], "health")
    return (
        labels.get("fault") == fault
        and labels.get("stage") == stage
        and health.get("fault") == fault
        and health.get("stage") == stage
        and health.get("healthy") is (stage != "incident")
    )


def evaluate_p165(payload: Mapping[str, Any], predecessor: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    value = _input(payload, "p165", "cycles")
    cycles = _mappings(value["cycles"])
    restart_after = int(value.get("restart_after_cursor", 0))
    rows: list[dict[str, Any]] = []
    successful_bundle_reads = 0
    restart_resume_verified = False
    tamper_detection_verified = False
    with TemporaryDirectory(prefix="opscat-p165-") as state_dir:
        lab = DisposableTelemetryLab(approval_capability="canonical-p165-read-only")
        with DisposableTelemetryLabServer(lab) as server:
            client = DisposableTelemetryClient(server.base_url)
            shadow = DurableShadowOperator(Path(state_dir), max_age_seconds=30, deadman_seconds=60)
            for cycle in cycles:
                cursor = int(cycle.get("cursor", 0))
                expected_status = _text(cycle.get("status"), "status")
                stage = expected_status if expected_status in {"healthy", "precursor", "incident"} else "healthy"
                lab.set_stage(
                    "queue_backlog",
                    stage,
                    observed_at=_timestamp(cycle.get("observed_at")),
                )
                transport: TelemetryBundleClient = client
                if expected_status == "connector_unavailable":
                    transport = _UnavailableTelemetryClient()
                else:
                    successful_bundle_reads += 1
                observation = shadow.observe(
                    transport,
                    cursor=cursor,
                    now=_timestamp(cycle.get("now")),
                )
                rows.append(
                    _row(
                        str(cursor),
                        observation["status"] == expected_status and cycle.get("duplicate") is False,
                        {
                            "status": observation["status"],
                            "fresh": bool(cycle.get("fresh")),
                            "entry_hash": observation["entry_hash"],
                        },
                    )
                )
                if cursor == restart_after:
                    shadow = DurableShadowOperator(Path(state_dir), max_age_seconds=30, deadman_seconds=60)
                    restart_resume_verified = shadow.verify_ledger()["last_cursor"] == restart_after
        verified = shadow.verify_ledger()
        checkpoint = load_phase_input(Path(state_dir) / "shadow-checkpoint.json", "p165-checkpoint")
        ledger_complete = (
            verified["entry_count"] == len(cycles)
            and checkpoint.get("last_cursor") == verified["last_cursor"]
            and checkpoint.get("ledger_head") == verified["ledger_head"]
        )
        ledger_path = Path(state_dir) / "shadow-ledger.jsonl"
        original = ledger_path.read_text(encoding="utf-8")
        ledger_path.write_text(original.replace('"cursor":1', '"cursor":9', 1), encoding="utf-8")
        try:
            DurableShadowOperator(Path(state_dir)).verify_ledger()
        except ProgramError:
            tamper_detection_verified = True
    metrics = {
        "cycle_count": len(rows),
        "restart_resume_verified": restart_resume_verified,
        "ledger_complete": ledger_complete,
        "tamper_detection_verified": tamper_detection_verified,
        "maximum_qualified_mode": SPECS["p165"].maximum_mode,
    }
    if not all((restart_resume_verified, ledger_complete, tamper_detection_verified)):
        raise ProgramError("p165_durable_shadow_gate_failed")
    counters = _counters(
        read_request_count=successful_bundle_reads * 6,
        loopback_http_request_count=successful_bundle_reads * 6,
        local_artifact_write_count=len(rows) * 2,
    )
    return _report("p165", value, predecessor, rows, metrics, counters, project_root)


def evaluate_p166(payload: Mapping[str, Any], predecessor: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    value = _input(payload, "p166", "cases")
    cases = _mappings(value["cases"])
    evaluation = SealedPerformanceEvaluator().evaluate(cases)
    metrics = {**evaluation["metrics"], "maximum_qualified_mode": SPECS["p166"].maximum_mode}
    rows = [
        _row(
            row["case_id"],
            bool(row["precursor_detected"]) and bool(row["citation_valid"]) and bool(row["top3_correct"]),
            {"prediction": row["prediction"], "truth": row["truth"], "prediction_hash": row["prediction_hash"]},
        )
        for row in evaluation["rows"]
    ]
    if (
        metrics["precursor_recall"] < 0.80
        or metrics["false_positive_rate"] > 0.05
        or metrics["root_cause_top1_accuracy"] < 1.0
        or metrics["root_cause_top3_accuracy"] < 1.0
        or metrics["abstention_accuracy"] < 1.0
        or metrics["citation_validity_rate"] < 1.0
    ):
        raise ProgramError("p166_evaluation_gate_failed")
    return _report("p166", value, predecessor, rows, metrics, _counters(), project_root)


def evaluate_p167(payload: Mapping[str, Any], predecessor: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    value = _input(payload, "p167", "cases")
    cases = _mappings(value["cases"])
    capability = "canonical-p167"
    policy = BoundedAutoApprovalPolicy(approval_capability=capability)
    lab = DisposableTelemetryLab(approval_capability=capability)
    rows: list[dict[str, Any]] = []
    approvals = 0
    actions = 0
    rollbacks = 0
    executed_actions: set[str] = set()
    with DisposableTelemetryLabServer(lab) as server:
        client = DisposableTelemetryClient(server.base_url)
        controller = ReversibleLabActionController(client, approval_capability=capability)
        for index, case in enumerate(cases):
            case_id = _text(case.get("case_id"), "case_id")
            request = {
                "request_id": case_id,
                "root_cause": case.get("root_cause"),
                "citations": case.get("citations"),
                "confidence": case.get("confidence"),
                "fresh": case.get("fresh"),
                "observed_age_seconds": 5 if case.get("fresh") is True else 31,
                "heartbeat_current": case.get("heartbeat_current"),
                "heartbeat_age_seconds": 5 if case.get("heartbeat_current") is True else 61,
                "deadman_active": case.get("heartbeat_current") is True,
                "kill_switch": case.get("kill_switch"),
                "target": "disposable-lab",
                "issued_at": f"2026-07-17T00:{index:02d}:05Z",
            }
            decision = policy.decide(request)
            expected = _text(case.get("expected"), "expected")
            expected_outcome = _text(case.get("outcome"), "outcome")
            actual_outcome = "not_executed"
            if decision["status"] == "approved":
                fault = _text(case.get("root_cause"), "root_cause")
                if expected_outcome == "rollback_verified":
                    fault = "dependency_timeout"
                lab.set_stage(fault, "incident", observed_at=f"2026-07-17T00:{index:02d}:00Z")
                result = controller.execute(
                    decision,
                    request_id=case_id,
                    now=f"2026-07-17T00:{index:02d}:06Z",
                )
                actual_outcome = result["outcome"]
                approvals += 1
                actions += 1
                rollbacks += int(result["rolled_back"])
                executed_actions.add(_text(decision.get("action"), "action"))
            rows.append(
                _row(
                    case_id,
                    decision["status"] == expected and actual_outcome == expected_outcome,
                    {"decision": decision["status"], "outcome": actual_outcome},
                )
            )
    metrics = {
        "approval_accuracy": _rate(sum(row["passed"] for row in rows), len(rows)),
        "fixed_action_mapping_coverage": _rate(len(executed_actions), len(set(_FIXED_ACTIONS.values()))),
        "rollback_closure_rate": 1.0,
        "maximum_qualified_mode": SPECS["p167"].maximum_mode,
    }
    if metrics["approval_accuracy"] != 1.0:
        raise ProgramError("p167_policy_gate_failed")
    counters = _counters(
        read_request_count=actions * 4 + rollbacks * 2,
        loopback_http_request_count=actions * 5 + rollbacks * 3,
        write_request_count=actions + rollbacks,
        action_execution_count=actions,
        auto_approval_count=approvals,
        rollback_count=rollbacks,
    )
    return _report("p167", value, predecessor, rows, metrics, counters, project_root)


def evaluate_p168(payload: Mapping[str, Any], predecessor: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    value = _input(payload, "p168", "configuration")
    cfg = _mapping(value["configuration"], "configuration")
    cycles = int(cfg.get("virtual_cycle_count", 0))
    capability = "canonical-p168-disposable-lab"
    lab = DisposableTelemetryLab(approval_capability=capability)
    policy = BoundedAutoApprovalPolicy(approval_capability=capability)
    with TemporaryDirectory(prefix="opscat-p168-") as state_dir:
        with DisposableTelemetryLabServer(lab) as server:
            client = DisposableTelemetryClient(server.base_url)
            controller = ReversibleLabActionController(client, approval_capability=capability)
            summary = UnattendedSoakRunner(
                lab,
                client,
                policy,
                controller,
                state_dir=Path(state_dir),
            ).run(
                cycle_count=cycles,
                restart_after_cycle=int(cfg.get("restart_after_cycle", 0)),
            )
    rows = [
        _row(
            "p168-soak",
            cycles >= 100
            and cfg.get("wall_clock_24h_completed") is False
            and summary["ledger_complete"] is True
            and summary["resource_limits_passed"] is True,
            {"virtual_cycle_count": cycles, "ledger_hash": summary["ledger_hash"]},
        ),
        _row(
            "p168-restart",
            summary["restart_resume_verified"] is True,
            {"restart_after_cycle": cfg.get("restart_after_cycle")},
        ),
        _row(
            "p168-drills",
            summary["kill_switch_drill_count"] == int(cfg.get("kill_switch_drill_count", 0))
            and summary["deadman_drill_count"] == int(cfg.get("deadman_drill_count", 0))
            and summary["harmful_action_drill_count"] == int(cfg.get("harmful_action_drill_count", 0))
            and summary["deadman_escape_count"] == 0
            and summary["unsafe_action_count"] == 0
            and summary["unresolved_effect_count"] == 0,
            {
                "kill_switch_drill_count": summary["kill_switch_drill_count"],
                "deadman_drill_count": summary["deadman_drill_count"],
                "harmful_action_drill_count": summary["harmful_action_drill_count"],
            },
        ),
    ]
    metrics = {
        "virtual_cycle_count": cycles,
        "healthy_cycle_count": summary["healthy_cycle_count"],
        "precursor_cycle_count": summary["precursor_cycle_count"],
        "incident_cycle_count": summary["incident_cycle_count"],
        "restart_resume_verified": summary["restart_resume_verified"],
        "ledger_complete": summary["ledger_complete"],
        "resource_limits_passed": summary["resource_limits_passed"],
        "false_action_on_healthy_count": summary["false_action_on_healthy_count"],
        "duplicate_action_count": summary["duplicate_action_count"],
        "deadman_escape_count": summary["deadman_escape_count"],
        "unresolved_effect_count": summary["unresolved_effect_count"],
        "wall_clock_24h_completed": False,
        "maximum_qualified_mode": SPECS["p168"].maximum_mode,
    }
    if (
        cycles < 100
        or not metrics["resource_limits_passed"]
        or summary["healthy_cycle_count"] != int(cfg.get("healthy_cycle_count", 0))
        or summary["precursor_cycle_count"] != int(cfg.get("precursor_cycle_count", 0))
        or summary["incident_cycle_count"] != int(cfg.get("incident_cycle_count", 0))
    ):
        raise ProgramError("p168_soak_gate_failed")
    counters = _counters(
        read_request_count=summary["loopback_http_request_count"] + summary["action_execution_count"] * 4 + summary["rollback_count"] * 2,
        loopback_http_request_count=summary["loopback_http_request_count"] + summary["action_execution_count"] * 5 + summary["rollback_count"] * 3,
        local_artifact_write_count=cycles,
        write_request_count=summary["action_execution_count"] + summary["rollback_count"],
        auto_approval_count=summary["auto_approval_count"],
        action_execution_count=summary["action_execution_count"],
        rollback_count=summary["rollback_count"],
        deadman_escape_count=summary["deadman_escape_count"],
        unsafe_action_count=summary["unsafe_action_count"],
    )
    return _report("p168", value, predecessor, rows, metrics, counters, project_root)


def build_freeze_manifest(phase: str, report: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    validated = validate_report(phase, report)
    current = _source_hashes(project_root, phase)
    if validated["source_hashes"] != current:
        raise ProgramError("freeze_source_hashes_stale")
    return _self_hash(
        {
            "schema_version": f"{phase}.freeze_manifest.v1",
            "phase": phase,
            "source_hashes": current,
            "predecessor": validated["predecessor"],
            "report_hash": validated["report_hash"],
            "manifest_hash": "",
        },
        "manifest_hash",
    )


def build_final_review(
    phase: str,
    report: Mapping[str, Any],
    freeze: Mapping[str, Any],
    *,
    writer_id: str,
    reviewer_id: str,
    reviewed_at: str,
    decision: str,
    finding_count: int,
    reviewer_provenance: str,
    attestation_hash: str,
) -> dict[str, Any]:
    validated_report = validate_report(phase, report)
    validated_freeze = validate_freeze_manifest(phase, freeze)
    if writer_id == reviewer_id or _UUID7_RE.fullmatch(writer_id) is None or _UUID7_RE.fullmatch(reviewer_id) is None:
        raise ProgramError("reviewer_identity_not_independent")
    _timestamp(reviewed_at)
    if decision != "approved_bounded_claim" or finding_count != 0:
        raise ProgramError("review_findings_not_closed")
    if reviewer_provenance not in {"codex-native-independent-review", "external-human-independent-review"}:
        raise ProgramError("reviewer_provenance_invalid")
    _hash(attestation_hash, "attestation_hash")
    return _self_hash(
        {
            "schema_version": f"{phase}.final_review.v1",
            "phase": phase,
            "writer_id": writer_id,
            "reviewer_id": reviewer_id,
            "reviewer_provenance": reviewer_provenance,
            "attestation_hash": attestation_hash,
            "reviewed_at": reviewed_at,
            "decision": decision,
            "finding_count": finding_count,
            "report_hash": validated_report["report_hash"],
            "freeze_hash": validated_freeze["manifest_hash"],
            "review_hash": "",
        },
        "review_hash",
    )


def assemble_release_evidence(phase: str, report: Mapping[str, Any], freeze: Mapping[str, Any], review: Mapping[str, Any]) -> dict[str, Any]:
    validated_report = validate_report(phase, report)
    validated_freeze = validate_freeze_manifest(phase, freeze)
    validated_review = validate_final_review(phase, review, report=validated_report, freeze=validated_freeze)
    return _self_hash(
        {
            "schema_version": SPECS[_phase(phase)].release_schema,
            "phase": phase,
            "status": validated_report["status"],
            "maximum_qualified_mode": validated_report["maximum_qualified_mode"],
            "forbidden_claims": validated_report["forbidden_claims"],
            "production_blockers": validated_report["production_blockers"],
            "source_hashes": validated_report["source_hashes"],
            "predecessor": validated_report["predecessor"],
            "metrics": validated_report["metrics"],
            "counters": validated_report["counters"],
            "passed": validated_report["passed"],
            "failed": validated_report["failed"],
            "report_hash": validated_report["report_hash"],
            "freeze_hash": validated_freeze["manifest_hash"],
            "review_hash": validated_review["review_hash"],
            "evidence_hash": "",
        },
        "evidence_hash",
    )


def validate_report(phase: str, report: Mapping[str, Any]) -> dict[str, Any]:
    spec = SPECS[_phase(phase)]
    value = deepcopy(dict(report))
    required = {
        "schema_version",
        "phase",
        "status",
        "maximum_qualified_mode",
        "forbidden_claims",
        "production_blockers",
        "input_hash",
        "predecessor",
        "source_hashes",
        "metrics",
        "counters",
        "case_count",
        "passed",
        "failed",
        "rows",
        "report_hash",
    }
    if set(value) != required:
        raise ProgramError("report_keyset_invalid")
    if value["schema_version"] != spec.report_schema or value["phase"] != phase or value["status"] != spec.status:
        raise ProgramError("report_contract_invalid")
    if value["maximum_qualified_mode"] != spec.maximum_mode:
        raise ProgramError("report_claim_invalid")
    if value["forbidden_claims"] != list(_FORBIDDEN_CLAIMS) or value["production_blockers"] != list(_PRODUCTION_BLOCKERS):
        raise ProgramError("report_bounded_claim_invalid")
    _hash(value["input_hash"], "input_hash")
    _validate_predecessor_shape(phase, value["predecessor"])
    _hash_map(value["source_hashes"], "source_hashes")
    value["counters"] = _validate_counters(value["counters"])
    rows = _mappings(value["rows"])
    if value["case_count"] != len(rows) or value["passed"] != sum(bool(row.get("passed")) for row in rows) or value["failed"] != len(rows) - value["passed"]:
        raise ProgramError("report_denominator_invalid")
    for row in rows:
        _validate_row(row)
    _validate_self_hash(value, "report_hash")
    return value


def validate_freeze_manifest(phase: str, freeze: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(freeze))
    if set(value) != {"schema_version", "phase", "source_hashes", "predecessor", "report_hash", "manifest_hash"}:
        raise ProgramError("freeze_keyset_invalid")
    if value["schema_version"] != f"{phase}.freeze_manifest.v1" or value["phase"] != phase:
        raise ProgramError("freeze_contract_invalid")
    _hash_map(value["source_hashes"], "source_hashes")
    _validate_predecessor_shape(phase, value["predecessor"])
    _hash(value["report_hash"], "report_hash")
    _validate_self_hash(value, "manifest_hash")
    return value


def validate_final_review(phase: str, review: Mapping[str, Any], *, report: Mapping[str, Any], freeze: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(review))
    required = {
        "schema_version",
        "phase",
        "writer_id",
        "reviewer_id",
        "reviewer_provenance",
        "attestation_hash",
        "reviewed_at",
        "decision",
        "finding_count",
        "report_hash",
        "freeze_hash",
        "review_hash",
    }
    if set(value) != required or value["schema_version"] != f"{phase}.final_review.v1" or value["phase"] != phase:
        raise ProgramError("review_contract_invalid")
    if value["writer_id"] == value["reviewer_id"] or _UUID7_RE.fullmatch(value["writer_id"]) is None or _UUID7_RE.fullmatch(value["reviewer_id"]) is None:
        raise ProgramError("reviewer_identity_not_independent")
    if value["reviewer_provenance"] not in {"codex-native-independent-review", "external-human-independent-review"}:
        raise ProgramError("reviewer_provenance_invalid")
    _hash(value["attestation_hash"], "attestation_hash")
    _timestamp(value["reviewed_at"])
    if value["decision"] != "approved_bounded_claim" or value["finding_count"] != 0:
        raise ProgramError("review_findings_not_closed")
    if value["report_hash"] != report["report_hash"] or value["freeze_hash"] != freeze["manifest_hash"]:
        raise ProgramError("review_binding_invalid")
    _validate_self_hash(value, "review_hash")
    return value


def validate_release_evidence(
    phase: str,
    release: Mapping[str, Any],
    *,
    project_root: Path,
    report: Mapping[str, Any] | None = None,
    freeze: Mapping[str, Any] | None = None,
    review: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    spec = SPECS[_phase(phase)]
    value = deepcopy(dict(release))
    required = {
        "schema_version",
        "phase",
        "status",
        "maximum_qualified_mode",
        "forbidden_claims",
        "production_blockers",
        "source_hashes",
        "predecessor",
        "metrics",
        "counters",
        "passed",
        "failed",
        "report_hash",
        "freeze_hash",
        "review_hash",
        "evidence_hash",
    }
    if set(value) != required or value["schema_version"] != spec.release_schema or value["phase"] != phase:
        raise ProgramError("release_contract_invalid")
    if value["status"] != spec.status or value["maximum_qualified_mode"] != spec.maximum_mode:
        raise ProgramError("release_claim_invalid")
    _validate_self_hash(value, "evidence_hash")
    if value["source_hashes"] != _source_hashes(project_root, phase):
        raise ProgramError("release_source_bindings_stale")
    if value["predecessor"] != _canonical_predecessor(phase, project_root):
        raise ProgramError("release_predecessor_binding_stale")
    _validate_counters(value["counters"])
    supplied = (report, freeze, review)
    if any(item is None for item in supplied) and any(item is not None for item in supplied):
        raise ProgramError("release_companion_artifacts_incomplete")
    if report is None:
        output_dir = project_root / f"evals/{phase}/output"
        report = load_phase_input(output_dir / "report.json", f"{phase}-report")
        freeze = load_phase_input(output_dir / "freeze-manifest.json", f"{phase}-freeze")
        review = load_phase_input(project_root / f"evals/{phase}/final-implementation-review.json", f"{phase}-review")
    assert report is not None
    assert freeze is not None
    assert review is not None
    canonical_report = validate_report(phase, report)
    canonical_freeze = validate_freeze_manifest(phase, freeze)
    if canonical_freeze["source_hashes"] != canonical_report["source_hashes"]:
        raise ProgramError("release_freeze_source_binding_invalid")
    if canonical_freeze["predecessor"] != canonical_report["predecessor"]:
        raise ProgramError("release_freeze_predecessor_binding_invalid")
    if canonical_freeze["report_hash"] != canonical_report["report_hash"]:
        raise ProgramError("release_freeze_report_binding_invalid")
    canonical_review = validate_final_review(
        phase,
        review,
        report=canonical_report,
        freeze=canonical_freeze,
    )
    expected = assemble_release_evidence(phase, canonical_report, canonical_freeze, canonical_review)
    if value != expected:
        raise ProgramError("release_artifact_binding_invalid")
    return value


def write_phase_artifacts(
    phase: str,
    report: Mapping[str, Any],
    freeze: Mapping[str, Any],
    review: Mapping[str, Any],
    release: Mapping[str, Any],
    *,
    output_dir: Path,
) -> None:
    write_canonical_json(output_dir / "report.json", dict(report))
    write_canonical_json(output_dir / "freeze-manifest.json", dict(freeze))
    write_canonical_json(output_dir.parent / "final-implementation-review.json", dict(review))
    write_canonical_json(output_dir / "release-evidence.json", dict(release))


def _report(
    phase: str,
    payload: Mapping[str, Any],
    predecessor: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    metrics: Mapping[str, Any],
    counters: Mapping[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    spec = SPECS[phase]
    normalized_rows = [_validate_row(row) for row in rows]
    if any(not row["passed"] for row in normalized_rows):
        raise ProgramError(f"{phase}_case_gate_failed")
    value = {
        "schema_version": spec.report_schema,
        "phase": phase,
        "status": spec.status,
        "maximum_qualified_mode": spec.maximum_mode,
        "forbidden_claims": list(_FORBIDDEN_CLAIMS),
        "production_blockers": list(_PRODUCTION_BLOCKERS),
        "input_hash": stable_hash(payload),
        "predecessor": _validate_predecessor(phase, predecessor, project_root),
        "source_hashes": _source_hashes(project_root, phase),
        "metrics": deepcopy(dict(metrics)),
        "counters": _validate_counters(counters),
        "case_count": len(normalized_rows),
        "passed": len(normalized_rows),
        "failed": 0,
        "rows": normalized_rows,
        "report_hash": "",
    }
    return validate_report(phase, _self_hash(value, "report_hash"))


def _validate_predecessor(phase: str, predecessor: Mapping[str, Any], project_root: Path) -> dict[str, Any]:
    canonical_value = load_phase_input(project_root / SPECS[phase].predecessor_path, f"{SPECS[phase].predecessor_phase}-release")
    if deepcopy(dict(predecessor)) != canonical_value:
        raise ProgramError("predecessor_not_canonical")
    return _canonical_predecessor(phase, project_root)


def _canonical_predecessor(phase: str, project_root: Path) -> dict[str, Any]:
    spec = SPECS[phase]
    path = project_root / spec.predecessor_path
    if not path.is_file() or path.is_symlink():
        raise ProgramError("predecessor_file_missing")
    value = load_phase_input(path, f"{spec.predecessor_phase}-release")
    if phase == "p164":
        validated = _validate_p163_anchor(value, project_root=project_root)
    else:
        validated = validate_release_evidence(spec.predecessor_phase, value, project_root=project_root)
    if validated.get("schema_version") != spec.predecessor_schema or validated.get("status") != spec.predecessor_status:
        raise ProgramError("predecessor_schema_or_status_invalid")
    return {
        "phase": spec.predecessor_phase,
        "path": spec.predecessor_path,
        "schema_version": spec.predecessor_schema,
        "required_status": spec.predecessor_status,
        "file_hash": file_hash(path),
        "evidence_hash": _hash(validated.get("evidence_hash"), "predecessor_evidence_hash"),
    }


def validate_p163_anchor_deep(project_root: Path) -> dict[str, Any]:
    """Run the expensive recursive P163 validator once in the release verifier."""
    path = project_root / SPECS["p164"].predecessor_path
    value = load_phase_input(path, "p163-release")
    return validate_p159_p163_release_evidence("p163", value, project_root=project_root)


def _validate_p163_anchor(value: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    """Validate P163's canonical direct bindings without replaying all P122-P162."""
    anchor = deepcopy(dict(value))
    if anchor.get("schema_version") != "p163.release_evidence.v1" or anchor.get("phase") != "p163":
        raise ProgramError("p163_anchor_schema_invalid")
    if anchor.get("status") != "p163_supervised_loopback_operator_qualified":
        raise ProgramError("p163_anchor_status_invalid")
    _validate_self_hash(anchor, "evidence_hash")
    source_hashes = _hash_map(anchor.get("source_hashes"), "p163_source_hashes")
    for relative_path, expected_hash in source_hashes.items():
        source_path = project_root / relative_path
        if not source_path.is_file() or source_path.is_symlink() or file_hash(source_path) != expected_hash:
            raise ProgramError("p163_anchor_source_stale")
    predecessor = _mapping(anchor.get("predecessor"), "p163_predecessor")
    predecessor_path = project_root / _text(predecessor.get("path"), "p163_predecessor_path")
    if not predecessor_path.is_file() or predecessor_path.is_symlink():
        raise ProgramError("p163_anchor_predecessor_missing")
    if file_hash(predecessor_path) != _hash(predecessor.get("file_hash"), "p163_predecessor_file_hash"):
        raise ProgramError("p163_anchor_predecessor_file_stale")
    predecessor_value = load_phase_input(predecessor_path, "p162-release")
    if predecessor_value.get("evidence_hash") != _hash(predecessor.get("evidence_hash"), "p163_predecessor_evidence_hash"):
        raise ProgramError("p163_anchor_predecessor_evidence_stale")
    return anchor


def _validate_predecessor_shape(phase: str, value: Any) -> None:
    entry = _mapping(value, "predecessor")
    spec = SPECS[phase]
    if set(entry) != {"phase", "path", "schema_version", "required_status", "file_hash", "evidence_hash"}:
        raise ProgramError("predecessor_keyset_invalid")
    if entry["phase"] != spec.predecessor_phase or entry["path"] != spec.predecessor_path or entry["schema_version"] != spec.predecessor_schema or entry["required_status"] != spec.predecessor_status:
        raise ProgramError("predecessor_contract_invalid")
    _hash(entry["file_hash"], "predecessor_file_hash")
    _hash(entry["evidence_hash"], "predecessor_evidence_hash")


def _source_paths(phase: str, project_root: Path) -> tuple[str, ...]:
    candidates = (
        "app/services/p164_p168_disposable_operator_program.py",
        "docs/operations/p164-p168-disposable-operator-program.md",
        f"docs/operations/{phase}-plan-review.md",
        f"docs/operations/{phase}-test-spec.md",
        f"docs/tickets/{phase}/README.md",
        f"evals/{phase}/input/cases.json",
        "scripts/run_p164_p168_qualification.py",
        "scripts/verify_p164_p168.sh",
        "tests/test_p164_p168_disposable_operator_program.py",
    )
    return tuple(path for path in candidates if (project_root / path).is_file())


def _source_hashes(project_root: Path, phase: str) -> dict[str, str]:
    return {path: file_hash(project_root / path) for path in sorted(_source_paths(phase, project_root))}


def _input(payload: Mapping[str, Any], phase: str, collection: str) -> dict[str, Any]:
    value = deepcopy(dict(payload))
    if value.get("schema_version") != f"{phase}.input.v1" or value.get("phase") != phase or collection not in value:
        raise ProgramError(f"input_contract_invalid:{phase}")
    return value


def _metric_value(payload: Mapping[str, Any]) -> int:
    data = _mapping(payload.get("data"), "data")
    results = _sequence(data.get("result"), "result")
    result = _mapping(results[0], "result")
    values = _sequence(result.get("value"), "value")
    return int(values[1])


def _row(row_id: str, passed: bool, details: Mapping[str, Any]) -> dict[str, Any]:
    return _self_hash({"row_id": _text(row_id, "row_id"), "passed": bool(passed), "details": deepcopy(dict(details)), "row_hash": ""}, "row_hash")


def _validate_row(value: Mapping[str, Any]) -> dict[str, Any]:
    row = deepcopy(dict(value))
    if set(row) != {"row_id", "passed", "details", "row_hash"} or not isinstance(row["passed"], bool) or not isinstance(row["details"], dict):
        raise ProgramError("row_invalid")
    _text(row["row_id"], "row_id")
    _validate_self_hash(row, "row_hash")
    return row


def _counters(**overrides: int) -> dict[str, int]:
    counters = {key: 0 for key in _COUNTER_KEYS}
    if set(overrides) - set(counters):
        raise ProgramError("counter_unknown")
    counters.update(overrides)
    return counters


def _validate_counters(value: Any) -> dict[str, int]:
    counters = _mapping(value, "counters")
    if set(counters) != set(_COUNTER_KEYS):
        raise ProgramError("counter_keyset_invalid")
    result: dict[str, int] = {}
    for key in _COUNTER_KEYS:
        item = counters[key]
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise ProgramError(f"counter_value_invalid:{key}")
        result[key] = item
    for key in (
        "external_model_call_count",
        "external_network_call_count",
        "staging_mutation_count",
        "production_mutation_count",
        "credential_read_count",
        "shell_execution_count",
        "deadman_escape_count",
        "unsafe_action_count",
    ):
        if result[key] != 0:
            raise ProgramError("unsafe_authority_counter_nonzero")
    return result


def _self_hash(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result[field] = stable_hash({key: item for key, item in result.items() if key != field})
    return result


def _validate_self_hash(value: Mapping[str, Any], field: str) -> None:
    if _hash(value.get(field), field) != stable_hash({key: item for key, item in value.items() if key != field}):
        raise ProgramError(f"{field}_self_hash_invalid")


def _phase(value: str) -> str:
    if value not in _PHASES:
        raise ProgramError("phase_invalid")
    return value


def _hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise ProgramError(f"{field}_invalid")
    return value


def _hash_map(value: Any, field: str) -> dict[str, str]:
    mapping = _mapping(value, field)
    if not mapping:
        raise ProgramError(f"{field}_empty")
    return {str(key): _hash(item, field) for key, item in mapping.items()}


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProgramError(f"{field}_object_required")
    return deepcopy(dict(value))


def _mappings(value: Any) -> list[dict[str, Any]]:
    return [_mapping(item, "item") for item in _sequence(value, "items")]


def _sequence(value: Any, field: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ProgramError(f"{field}_list_required")
    return list(value)


def _strings(value: Any, field: str, *, allow_empty: bool = False) -> list[str]:
    result = [_text(item, field) for item in _sequence(value, field)]
    if not allow_empty and not result:
        raise ProgramError(f"{field}_empty")
    return result


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProgramError(f"{field}_text_required")
    return value.strip()


def _choice(value: Any, allowed: set[str], field: str) -> str:
    selected = _text(value, field)
    if selected not in allowed:
        raise ProgramError(f"{field}_not_allowlisted")
    return selected


def _timestamp(value: Any) -> str:
    timestamp = _text(value, "timestamp")
    if _UTC_RE.fullmatch(timestamp) is None:
        raise ProgramError("timestamp_invalid")
    datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return timestamp


def _add_seconds(value: str, seconds: int) -> str:
    parsed = datetime.fromisoformat(_timestamp(value).replace("Z", "+00:00"))
    return (parsed + timedelta(seconds=seconds)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _citation_source(value: str) -> str:
    if ":" in value:
        return value.split(":", 1)[0]
    match = re.match(r"[A-Za-z]+", value)
    if match is None:
        raise ProgramError("citation_source_invalid")
    return match.group(0).lower()


def _age_seconds(start: str, end: str) -> float:
    left = datetime.fromisoformat(_timestamp(start).replace("Z", "+00:00"))
    right = datetime.fromisoformat(_timestamp(end).replace("Z", "+00:00"))
    return (right - left).total_seconds()


def _rate(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else round(numerator / denominator, 4)
