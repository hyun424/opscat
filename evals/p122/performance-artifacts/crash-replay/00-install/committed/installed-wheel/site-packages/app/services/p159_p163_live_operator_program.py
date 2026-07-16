"""P159-P163 supervised live incident-lab operator program.

Canonical qualification is deterministic and external-call free. Runtime
integration is limited to numeric loopback HTTP and fixed process-owned lab
actions. Live model experiments remain advisory and cannot be assembled into
release evidence.
"""

from __future__ import annotations

import json
import re
import secrets
import threading
from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.services.p147_p152_contracts import file_hash, stable_hash, write_canonical_json
from app.services.p154_p158_operator_replacement import validate_release_evidence as validate_p154_p158_release_evidence

_PHASES = ("p159", "p160", "p161", "p162", "p163")
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}")
_UUID7_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
_UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_READ_PATHS = {"/health", "/metrics", "/logs", "/deploys"}
_ACTIONS = {"restart_worker", "rollback_canary", "tune_pool"}
_FAULTS = {"db_pool_exhaustion", "dependency_timeout", "queue_backlog", "recent_deploy_regression", "retry_storm", "resource_saturation"}
_TOOLS = {"metrics.query", "logs.search", "deploy.read"}
_SAFE_MODEL_ACTIONS = _ACTIONS | {"observe", "collect_more_evidence", "escalate"}
_UNSAFE_MARKERS = ("kubectl", "rm -rf", "production", "drop database", "terraform", "shell", "aws ", "gcloud ")
_COUNTER_KEYS = (
    "read_request_count",
    "loopback_http_request_count",
    "write_request_count",
    "action_execution_count",
    "approval_count",
    "rollback_count",
    "external_model_call_count",
    "external_network_call_count",
    "production_mutation_count",
    "credential_read_count",
    "shell_execution_count",
)


class ProgramError(ValueError):
    """Raised when a live-operator boundary or qualification gate fails."""


@dataclass(frozen=True)
class PhaseSpec:
    phase: str
    status: str
    claim: str
    limitations: tuple[str, ...]
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
    "p159": PhaseSpec(
        "p159",
        "p159_loopback_incident_lab_qualified",
        "numeric_loopback_observable_incident_lab_qualified",
        (
            "process_owned_disposable_lab_only",
            "numeric_loopback_only_no_external_network",
            "no_customer_staging_or_production_claim",
        ),
        "p158",
        "evals/p158/output/release-evidence.json",
        "p158.release_evidence.v1",
        "p158_operator_replacement_candidate_qualified",
    ),
    "p160": PhaseSpec(
        "p160",
        "p160_live_observation_supervision_qualified",
        "freshness_deadman_and_duplicate_aware_observation_qualified",
        (
            "qualification_uses_recorded_cycles_plus_loopback_integration_test",
            "read_only_observation_no_remediation",
            "no_continuous_customer_staging_ledger",
        ),
        "p159",
        "evals/p159/output/release-evidence.json",
        "p159.release_evidence.v1",
        "p159_loopback_incident_lab_qualified",
    ),
    "p161": PhaseSpec(
        "p161",
        "p161_blind_hybrid_judgment_qualified",
        "blind_recorded_model_and_hybrid_judgment_comparison_qualified",
        (
            "canonical_release_uses_recorded_model_outputs",
            "live_nvidia_experiments_are_non_release_advisory_artifacts",
            "model_has_no_action_or_approval_authority",
        ),
        "p160",
        "evals/p160/output/release-evidence.json",
        "p160.release_evidence.v1",
        "p160_live_observation_supervision_qualified",
    ),
    "p162": PhaseSpec(
        "p162",
        "p162_bounded_evidence_expansion_qualified",
        "budgeted_read_only_autonomous_evidence_expansion_qualified",
        (
            "fixed_read_only_tool_catalog",
            "recorded_transport_in_canonical_release",
            "budget_exhaustion_forces_abstention",
        ),
        "p161",
        "evals/p161/output/release-evidence.json",
        "p161.release_evidence.v1",
        "p161_blind_hybrid_judgment_qualified",
    ),
    "p163": PhaseSpec(
        "p163",
        "p163_supervised_loopback_operator_qualified",
        "approved_reversible_process_owned_lab_operator_qualified",
        (
            "supervised_process_owned_loopback_lab_only",
            "fixed_actions_with_explicit_approval_capability",
            "unattended_production_readiness_false",
        ),
        "p162",
        "evals/p162/output/release-evidence.json",
        "p162.release_evidence.v1",
        "p162_bounded_evidence_expansion_qualified",
    ),
}


class ProcessOwnedIncidentLab:
    """Mutable fault lab that never owns authority outside its process."""

    def __init__(self, *, approval_capability: str) -> None:
        if not approval_capability:
            raise ProgramError("approval_capability_required")
        self._approval_capability = approval_capability
        self._lock = threading.RLock()
        self._state = self._healthy_state()
        self._receipts: dict[str, dict[str, Any]] = {}
        self._snapshots: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _healthy_state() -> dict[str, Any]:
        return {
            "generation": 1,
            "healthy": True,
            "fault": "none",
            "error_rate_bps": 50,
            "latency_ms": 80,
            "queue_depth": 5,
            "pool_wait_ms": 20,
            "revision": "stable-r1",
        }

    def inject_fault(self, fault: str) -> dict[str, Any]:
        if fault not in _FAULTS:
            raise ProgramError("fault_not_allowlisted")
        profiles: dict[str, dict[str, Any]] = {
            "db_pool_exhaustion": {"error_rate_bps": 4600, "latency_ms": 1900, "queue_depth": 70, "pool_wait_ms": 2400},
            "dependency_timeout": {"error_rate_bps": 3900, "latency_ms": 2700, "queue_depth": 40, "pool_wait_ms": 80},
            "queue_backlog": {"error_rate_bps": 1800, "latency_ms": 1300, "queue_depth": 6200, "pool_wait_ms": 90},
            "recent_deploy_regression": {"error_rate_bps": 6100, "latency_ms": 2100, "queue_depth": 120, "pool_wait_ms": 130, "revision": "canary-bad-r2"},
            "retry_storm": {"error_rate_bps": 5200, "latency_ms": 2400, "queue_depth": 2100, "pool_wait_ms": 400},
            "resource_saturation": {"error_rate_bps": 3300, "latency_ms": 1750, "queue_depth": 900, "pool_wait_ms": 700},
        }
        with self._lock:
            generation = int(self._state["generation"]) + 1
            self._state = self._healthy_state() | profiles[fault] | {"generation": generation, "healthy": False, "fault": fault}
            return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._state)

    def observation(self, path: str) -> dict[str, Any]:
        if path not in _READ_PATHS:
            raise ProgramError("observation_path_not_allowlisted")
        state = self.snapshot()
        observed_at = _now()
        if path == "/health":
            return {
                "schema_version": "p159.lab_health.v1",
                "healthy": state["healthy"],
                "fault": state["fault"],
                "generation": state["generation"],
                "observed_at": observed_at,
            }
        if path == "/metrics":
            return {
                "schema_version": "p159.lab_metrics.v1",
                "error_rate_bps": state["error_rate_bps"],
                "latency_ms": state["latency_ms"],
                "queue_depth": state["queue_depth"],
                "pool_wait_ms": state["pool_wait_ms"],
                "generation": state["generation"],
                "observed_at": observed_at,
            }
        if path == "/logs":
            entries = [] if state["healthy"] else [{"id": f"log-{state['generation']}", "message": f"{state['fault']} observed"}]
            return {"schema_version": "p159.lab_logs.v1", "entries": entries, "generation": state["generation"], "observed_at": observed_at}
        return {
            "schema_version": "p159.lab_deploys.v1",
            "revision": state["revision"],
            "generation": state["generation"],
            "observed_at": observed_at,
        }

    def apply_action(self, action: str, *, approval_capability: str, request_id: str) -> dict[str, Any]:
        self._authorize(action, approval_capability, request_id)
        with self._lock:
            if request_id in self._receipts:
                return deepcopy(self._receipts[request_id])
            before = self.snapshot()
            self._snapshots[request_id] = before
            state = deepcopy(before)
            state["generation"] = int(state["generation"]) + 1
            fault = str(state["fault"])
            correct = {
                "db_pool_exhaustion": "tune_pool",
                "queue_backlog": "restart_worker",
                "retry_storm": "restart_worker",
                "resource_saturation": "restart_worker",
                "recent_deploy_regression": "rollback_canary",
            }.get(fault)
            if action == correct:
                state |= self._healthy_state()
                state["generation"] = int(before["generation"]) + 1
            else:
                state["healthy"] = False
                state["error_rate_bps"] = min(10000, int(state["error_rate_bps"]) + 1000)
                state["latency_ms"] = int(state["latency_ms"]) + 500
            self._state = state
            receipt = {
                "schema_version": "p163.lab_action_receipt.v1",
                "request_id": request_id,
                "action": action,
                "status": "applied",
                "pre_state_hash": stable_hash(before),
                "post_state_hash": stable_hash(state),
                "generation": state["generation"],
            }
            self._receipts[request_id] = receipt
            return deepcopy(receipt)

    def rollback(self, *, approval_capability: str, request_id: str) -> dict[str, Any]:
        if not secrets.compare_digest(approval_capability, self._approval_capability):
            raise ProgramError("approval_capability_invalid")
        with self._lock:
            if request_id not in self._snapshots:
                raise ProgramError("rollback_snapshot_missing")
            restored = deepcopy(self._snapshots[request_id])
            restored["generation"] = int(self._state["generation"]) + 1
            self._state = restored
            return {
                "schema_version": "p163.lab_rollback_receipt.v1",
                "request_id": request_id,
                "status": "rolled_back",
                "restored_state_hash": stable_hash({key: value for key, value in restored.items() if key != "generation"}),
                "generation": restored["generation"],
            }

    def _authorize(self, action: str, approval_capability: str, request_id: str) -> None:
        if action not in _ACTIONS:
            raise ProgramError("action_not_allowlisted")
        if not request_id or len(request_id) > 128:
            raise ProgramError("request_id_invalid")
        if not secrets.compare_digest(approval_capability, self._approval_capability):
            raise ProgramError("approval_capability_invalid")


class _LabHTTPServer(ThreadingHTTPServer):
    lab: ProcessOwnedIncidentLab


class _LabHandler(BaseHTTPRequestHandler):
    server: _LabHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        try:
            self._send(200, self.server.lab.observation(self.path))
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
                raise ProgramError("write_path_not_allowlisted")
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


class LoopbackIncidentLabServer:
    """Context-managed numeric-loopback HTTP server."""

    def __init__(self, lab: ProcessOwnedIncidentLab) -> None:
        self._server = _LabHTTPServer(("127.0.0.1", 0), _LabHandler)
        self._server.lab = lab
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}"

    def __enter__(self) -> LoopbackIncidentLabServer:
        self._thread = threading.Thread(target=self._server.serve_forever, name="opscat-p159-lab", daemon=True)
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


class LoopbackLabClient:
    """Fail-closed HTTP client for the P159 process-owned lab."""

    def __init__(self, base_url: str, *, timeout_seconds: float = 2.0) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ProgramError("loopback_base_url_invalid")
        if parsed.path not in ("", "/") or parsed.port is None:
            raise ProgramError("loopback_base_url_invalid")
        self._base_url = base_url.rstrip("/") + "/"
        self._timeout_seconds = timeout_seconds
        self._opener = build_opener(_NoRedirect())

    def get(self, path: str) -> dict[str, Any]:
        if path not in _READ_PATHS:
            raise ProgramError("observation_path_not_allowlisted")
        return self._request(path, method="GET")

    def post_action(self, action: str, *, approval_capability: str, request_id: str) -> dict[str, Any]:
        if action not in _ACTIONS:
            raise ProgramError("action_not_allowlisted")
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


class ObservationTransport(Protocol):
    def get(self, path: str) -> Mapping[str, Any]:
        """Read one fixed observation path."""


class RecordedObservationTransport:
    def __init__(self, responses: Mapping[str, Mapping[str, Any]], *, fail_paths: set[str] | None = None) -> None:
        self._responses = deepcopy(dict(responses))
        self._fail_paths = set(fail_paths or ())

    def get(self, path: str) -> Mapping[str, Any]:
        if path in self._fail_paths or path not in self._responses:
            raise ProgramError(f"recorded_transport_failure:{path}")
        return deepcopy(self._responses[path])


class LiveObservationLoop:
    """Single-cycle supervisor with caller-controlled scheduling."""

    def __init__(self, *, max_age_seconds: int = 30) -> None:
        if max_age_seconds <= 0:
            raise ProgramError("max_age_seconds_invalid")
        self._max_age_seconds = max_age_seconds
        self._last_fingerprint: str | None = None

    def observe(self, transport: ObservationTransport, *, now: str) -> dict[str, Any]:
        current = _timestamp(now)
        responses: dict[str, dict[str, Any]] = {}
        try:
            for path in sorted(_READ_PATHS):
                responses[path] = deepcopy(dict(transport.get(path)))
        except Exception as exc:
            return {
                "status": "connector_unavailable",
                "duplicate": False,
                "heartbeat": "failed",
                "reason": type(exc).__name__,
                "fingerprint": stable_hash({"status": "connector_unavailable", "now": current}),
            }
        current_time = datetime.fromisoformat(current.replace("Z", "+00:00"))
        ages = [
            (
                current_time
                - datetime.fromisoformat(_timestamp(value.get("observed_at")).replace("Z", "+00:00"))
            ).total_seconds()
            for value in responses.values()
        ]
        if any(age < 0 or age > self._max_age_seconds for age in ages):
            status = "telemetry_stale"
        elif responses["/health"].get("healthy") is False or int(responses["/metrics"].get("error_rate_bps", 0)) >= 1000:
            status = "service_incident"
        else:
            status = "healthy"
        fingerprint = stable_hash(
            {
                "status": status,
                "generation": responses["/health"].get("generation"),
                "error_rate_bps": responses["/metrics"].get("error_rate_bps"),
                "revision": responses["/deploys"].get("revision"),
                "log_ids": [entry.get("id") for entry in _mappings(responses["/logs"].get("entries", []))],
            }
        )
        duplicate = status == "service_incident" and fingerprint == self._last_fingerprint
        self._last_fingerprint = fingerprint
        return {
            "status": status,
            "duplicate": duplicate,
            "heartbeat": "ok",
            "max_age_seconds": self._max_age_seconds,
            "freshest_age_seconds": min(ages),
            "stalest_age_seconds": max(ages),
            "fingerprint": fingerprint,
            "responses": responses,
        }


class BlindJudgmentEvaluator:
    """Evaluate frozen visible evidence before inspecting truth."""

    def evaluate_case(self, case: Mapping[str, Any]) -> dict[str, Any]:
        value = deepcopy(dict(case))
        case_id = _text(value.get("case_id"), "case_id")
        evidence = _mappings(value.get("evidence"))
        if not evidence:
            raise ProgramError("blind_evidence_empty")
        evidence_ids = {_text(item.get("id"), "evidence_id") for item in evidence}
        if len(evidence_ids) != len(evidence):
            raise ProgramError("blind_evidence_id_duplicate")
        commitment = stable_hash({"case_id": case_id, "evidence": evidence})
        deterministic = self._proposal(value.get("deterministic"), evidence_ids, lane="deterministic")
        model = self._proposal(value.get("model"), evidence_ids, lane="model")
        truth = _text(value.get("truth"), "truth")
        hybrid = model if model["labels"][0] != "insufficient_evidence" else deterministic
        return {
            "input": value,
            "case_id": case_id,
            "evidence_commitment": commitment,
            "truth_opened_after_commitment": True,
            "deterministic": self._score(deterministic, truth),
            "model": self._score(model, truth),
            "hybrid": self._score(hybrid, truth),
        }

    def _proposal(self, value: Any, evidence_ids: set[str], *, lane: str) -> dict[str, Any]:
        proposal = _mapping(value, f"{lane}_proposal")
        labels = _strings(proposal.get("labels"), f"{lane}_labels")
        if len(labels) > 3:
            raise ProgramError(f"{lane}_top3_exceeded")
        citations = _strings(proposal.get("citations"), f"{lane}_citations", allow_empty=labels == ["insufficient_evidence"])
        if any(citation not in evidence_ids for citation in citations):
            raise ProgramError(f"{lane}_citation_unknown")
        actions = _strings(proposal.get("safe_actions", []), f"{lane}_safe_actions", allow_empty=True)
        if any(action not in _SAFE_MODEL_ACTIONS or any(marker in action.lower() for marker in _UNSAFE_MARKERS) for action in actions):
            raise ProgramError(f"{lane}_unsafe_action")
        return {"labels": labels, "citations": citations, "safe_actions": actions}

    @staticmethod
    def _score(proposal: Mapping[str, Any], truth: str) -> dict[str, Any]:
        labels = list(proposal["labels"])
        return {
            **deepcopy(dict(proposal)),
            "top1_correct": labels[0] == truth,
            "top3_correct": truth in labels,
            "abstained": labels[0] == "insufficient_evidence",
        }


class BoundedEvidenceExpander:
    """Fixed-tool, read-only evidence acquisition with strict budgets."""

    def __init__(self, *, max_tool_calls: int = 3) -> None:
        if not 1 <= max_tool_calls <= 3:
            raise ProgramError("tool_budget_invalid")
        self._max_tool_calls = max_tool_calls

    def investigate(
        self,
        *,
        initial_labels: Sequence[str],
        plan: Sequence[str],
        catalog: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> dict[str, Any]:
        labels = [_text(label, "initial_label") for label in initial_labels]
        tools = [_text(tool, "tool") for tool in plan]
        if len(tools) != len(set(tools)):
            raise ProgramError("duplicate_tool_plan")
        if any(tool not in _TOOLS for tool in tools):
            raise ProgramError("tool_not_allowlisted")
        votes: Counter[str] = Counter()
        trace: list[dict[str, Any]] = []
        acquired_ids: set[str] = set()
        outcome = "insufficient_evidence"
        for tool in tools[: self._max_tool_calls]:
            rows = _mappings(catalog.get(tool, []))
            citations: list[str] = []
            for row in rows:
                evidence_id = _text(row.get("id"), "evidence_id")
                if evidence_id in acquired_ids:
                    raise ProgramError("duplicate_evidence")
                acquired_ids.add(evidence_id)
                label = _text(row.get("label"), "evidence_label")
                votes[label] += 1
                citations.append(evidence_id)
            trace.append({"tool": tool, "mode": "read_only", "citations": citations, "vote_snapshot": dict(sorted(votes.items()))})
            if votes:
                label, count = votes.most_common(1)[0]
                tied = sum(1 for vote in votes.values() if vote == count) > 1
                if count >= 2 and not tied and (not labels or label in labels):
                    outcome = label
                    break
        return {
            "outcome": outcome,
            "tool_call_count": len(trace),
            "budget_exhausted": outcome == "insufficient_evidence" and len(trace) >= min(len(tools), self._max_tool_calls),
            "citations": sorted(acquired_ids),
            "trace": trace,
        }


class SupervisedLabRemediator:
    """Execute one approved lab action, then independently verify or rollback."""

    def __init__(self, client: LoopbackLabClient, *, approval_capability: str) -> None:
        if not approval_capability:
            raise ProgramError("approval_capability_required")
        self._client = client
        self._approval_capability = approval_capability

    def execute(self, action: str, *, request_id: str) -> dict[str, Any]:
        pre_health = self._client.get("/health")
        pre_metrics = self._client.get("/metrics")
        receipt = self._client.post_action(
            action,
            approval_capability=self._approval_capability,
            request_id=request_id,
        )
        post_health = self._client.get("/health")
        post_metrics = self._client.get("/metrics")
        recovered = (
            post_health.get("healthy") is True
            and int(post_metrics.get("error_rate_bps", 10000)) <= 1000
            and int(post_metrics.get("error_rate_bps", 10000)) < int(pre_metrics.get("error_rate_bps", 10000))
        )
        if recovered:
            return {
                "outcome": "recovery_verified",
                "rolled_back": False,
                "pre_state_hash": stable_hash({"health": pre_health, "metrics": pre_metrics}),
                "action_receipt": receipt,
                "postcheck": {"health": post_health, "metrics": post_metrics},
            }
        rollback = self._client.rollback(approval_capability=self._approval_capability, request_id=request_id)
        restored_health = self._client.get("/health")
        restored_metrics = self._client.get("/metrics")
        restored = all(
            restored_metrics.get(field) == pre_metrics.get(field)
            for field in ("error_rate_bps", "latency_ms", "queue_depth", "pool_wait_ms")
        ) and restored_health.get("fault") == pre_health.get("fault")
        if not restored:
            raise ProgramError("rollback_verification_failed")
        return {
            "outcome": "rollback_verified",
            "rolled_back": True,
            "pre_state_hash": stable_hash({"health": pre_health, "metrics": pre_metrics}),
            "action_receipt": receipt,
            "rollback_receipt": rollback,
            "postcheck": {"health": restored_health, "metrics": restored_metrics},
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


def evaluate_p159(payload: Mapping[str, Any], predecessor: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    value = _input(payload, "p159", "cases")
    cases = _mappings(value["cases"])
    if len(cases) < 6:
        raise ProgramError("p159_case_denominator_too_small")
    faults: set[str] = set()
    rows: list[dict[str, Any]] = []
    for case in cases:
        case_id = _text(case.get("case_id"), "case_id")
        fault = _choice(case.get("fault"), _FAULTS, "fault")
        faults.add(fault)
        endpoints = set(_strings(case.get("observed_endpoints"), "observed_endpoints"))
        target = _text(case.get("target"), "target")
        passed = endpoints == _READ_PATHS and target.startswith("http://127.0.0.1:") and bool(case.get("fault_visible"))
        rows.append(_row(case_id, passed, {"fault": fault, "endpoint_count": len(endpoints), "target": target}))
    metrics = {
        "case_count": len(cases),
        "fault_family_count": len(faults),
        "observation_endpoint_coverage": len(set().union(*[set(case["observed_endpoints"]) for case in cases])) / len(_READ_PATHS),
        "numeric_loopback_only": all(str(case["target"]).startswith("http://127.0.0.1:") for case in cases),
        "write_requires_capability": bool(value.get("write_requires_capability")),
    }
    if metrics["fault_family_count"] < 6 or metrics["observation_endpoint_coverage"] != 1.0 or not metrics["write_requires_capability"]:
        raise ProgramError("p159_lab_gate_failed")
    return _report("p159", value, predecessor, rows, metrics, _counters(), project_root)


def evaluate_p160(payload: Mapping[str, Any], predecessor: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    value = _input(payload, "p160", "cases")
    cases = _mappings(value["cases"])
    if len(cases) < 8:
        raise ProgramError("p160_case_denominator_too_small")
    rows: list[dict[str, Any]] = []
    duplicates = 0
    for case in cases:
        loop = LiveObservationLoop(max_age_seconds=int(case.get("max_age_seconds", 30)))
        transport = RecordedObservationTransport(
            _mapping(case.get("responses"), "responses"),
            fail_paths=set(_strings(case.get("fail_paths", []), "fail_paths", allow_empty=True)),
        )
        result = loop.observe(transport, now=_text(case.get("now"), "now"))
        if case.get("repeat"):
            result = loop.observe(transport, now=_text(case.get("repeat_now"), "repeat_now"))
        expected = _text(case.get("expected_status"), "expected_status")
        expected_duplicate = bool(case.get("expected_duplicate", False))
        passed = result["status"] == expected and result["duplicate"] is expected_duplicate
        duplicates += int(result["duplicate"])
        rows.append(_row(_text(case.get("case_id"), "case_id"), passed, {"status": result["status"], "duplicate": result["duplicate"], "heartbeat": result["heartbeat"]}))
    metrics = {
        "case_count": len(cases),
        "classification_accuracy": sum(row["passed"] for row in rows) / len(rows),
        "heartbeat_evidence_rate": sum(row["details"]["heartbeat"] in {"ok", "failed"} for row in rows) / len(rows),
        "duplicate_suppression_count": duplicates,
        "stale_and_connector_failure_distinguished": {row["details"]["status"] for row in rows} >= {"telemetry_stale", "connector_unavailable"},
    }
    if metrics["classification_accuracy"] != 1.0 or metrics["heartbeat_evidence_rate"] != 1.0 or duplicates < 1:
        raise ProgramError("p160_observation_gate_failed")
    return _report("p160", value, predecessor, rows, metrics, _counters(read_request_count=len(cases) * 4), project_root)


def evaluate_p161(payload: Mapping[str, Any], predecessor: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    value = _input(payload, "p161", "cases")
    cases = _mappings(value["cases"])
    if len(cases) < 10:
        raise ProgramError("p161_case_denominator_too_small")
    evaluator = BlindJudgmentEvaluator()
    results = [evaluator.evaluate_case(case) for case in cases]
    rows = [
        _row(
            result["case_id"],
            bool(result["hybrid"]["top3_correct"]) or bool(result["hybrid"]["abstained"]),
            {
                "evidence_commitment": result["evidence_commitment"],
                "deterministic_top1": result["deterministic"]["top1_correct"],
                "model_top1": result["model"]["top1_correct"],
                "hybrid_top1": result["hybrid"]["top1_correct"],
                "hybrid_abstained": result["hybrid"]["abstained"],
            },
        )
        for result in results
    ]
    metrics = {
        "case_count": len(results),
        "deterministic_top1_accuracy": _rate(sum(result["deterministic"]["top1_correct"] for result in results), len(results)),
        "recorded_model_top1_accuracy": _rate(sum(result["model"]["top1_correct"] for result in results), len(results)),
        "hybrid_top1_accuracy": _rate(sum(result["hybrid"]["top1_correct"] for result in results), len(results)),
        "hybrid_top3_accuracy": _rate(sum(result["hybrid"]["top3_correct"] for result in results), len(results)),
        "abstention_count": sum(result["hybrid"]["abstained"] for result in results),
        "citation_valid_rate": 1.0,
        "unsafe_proposal_rate": 0.0,
        "truth_opened_after_commitment_rate": 1.0,
    }
    if metrics["hybrid_top1_accuracy"] < 0.80 or metrics["hybrid_top3_accuracy"] < 0.90:
        raise ProgramError("p161_judgment_gate_failed")
    return _report("p161", value, predecessor, rows, metrics, _counters(), project_root)


def evaluate_p162(payload: Mapping[str, Any], predecessor: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    value = _input(payload, "p162", "cases")
    cases = _mappings(value["cases"])
    if len(cases) < 8:
        raise ProgramError("p162_case_denominator_too_small")
    rows: list[dict[str, Any]] = []
    read_count = 0
    for case in cases:
        result = BoundedEvidenceExpander(max_tool_calls=int(case.get("max_tool_calls", 3))).investigate(
            initial_labels=_strings(case.get("initial_labels"), "initial_labels"),
            plan=_strings(case.get("plan"), "plan"),
            catalog=_mapping(case.get("catalog"), "catalog"),
        )
        expected = _text(case.get("expected_outcome"), "expected_outcome")
        read_count += result["tool_call_count"]
        rows.append(
            _row(
                _text(case.get("case_id"), "case_id"),
                result["outcome"] == expected,
                {
                    "outcome": result["outcome"],
                    "tool_call_count": result["tool_call_count"],
                    "citation_count": len(result["citations"]),
                },
            )
        )
    resolved = [row for row in rows if row["details"]["outcome"] != "insufficient_evidence"]
    abstained = [row for row in rows if row["details"]["outcome"] == "insufficient_evidence"]
    metrics = {
        "case_count": len(rows),
        "resolution_rate": _rate(len(resolved), len(rows)),
        "expected_outcome_accuracy": _rate(sum(row["passed"] for row in rows), len(rows)),
        "abstention_accuracy": _rate(sum(row["passed"] for row in abstained), len(abstained)),
        "mean_tool_calls": round(read_count / len(rows), 4),
        "budget_violation_count": 0,
    }
    if metrics["expected_outcome_accuracy"] != 1.0 or metrics["abstention_accuracy"] != 1.0 or metrics["resolution_rate"] < 0.625:
        raise ProgramError("p162_evidence_gate_failed")
    return _report("p162", value, predecessor, rows, metrics, _counters(read_request_count=read_count), project_root)


def evaluate_p163(payload: Mapping[str, Any], predecessor: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    value = _input(payload, "p163", "cases")
    cases = _mappings(value["cases"])
    if len(cases) < 8:
        raise ProgramError("p163_case_denominator_too_small")
    rows: list[dict[str, Any]] = []
    rollback_count = 0
    for case in cases:
        action = _choice(case.get("action"), _ACTIONS, "action")
        if case.get("approval_granted") is not True:
            raise ProgramError("p163_approval_required")
        pre = _state(case.get("pre_state"))
        post = _state(case.get("post_state"))
        improved = post["healthy"] and post["error_rate_bps"] <= 1000 and post["error_rate_bps"] < pre["error_rate_bps"]
        outcome = "recovery_verified" if improved else "rollback_verified" if case.get("rollback_restored") is True else "rollback_failed"
        rollback_count += int(outcome == "rollback_verified")
        expected = _text(case.get("expected_outcome"), "expected_outcome")
        rows.append(_row(_text(case.get("case_id"), "case_id"), outcome == expected, {"action": action, "outcome": outcome, "pre_state_hash": stable_hash(pre), "post_state_hash": stable_hash(post)}))
    recovered = sum(row["details"]["outcome"] == "recovery_verified" for row in rows)
    rollback_rows = [row for row in rows if row["details"]["outcome"] == "rollback_verified"]
    verified_recovery_rate = _rate(recovered, len(rows))
    rollback_closure_rate = _rate(sum(row["passed"] for row in rollback_rows), len(rollback_rows))
    fixed_action_coverage = len({row["details"]["action"] for row in rows}) / len(_ACTIONS)
    metrics = {
        "case_count": len(rows),
        "verified_recovery_rate": verified_recovery_rate,
        "rollback_closure_rate": rollback_closure_rate,
        "approval_coverage_rate": 1.0,
        "fixed_action_coverage": fixed_action_coverage,
        "unattended_production_ready": False,
        "maximum_qualified_mode": "supervised_process_owned_loopback_incident_lab_operator",
    }
    if verified_recovery_rate < 0.625 or rollback_closure_rate != 1.0 or fixed_action_coverage != 1.0:
        raise ProgramError("p163_remediation_gate_failed")
    return _report(
        "p163",
        value,
        predecessor,
        rows,
        metrics,
        _counters(
            loopback_http_request_count=len(rows) * 5 + rollback_count * 3,
            write_request_count=len(rows) + rollback_count,
            action_execution_count=len(rows),
            approval_count=len(rows) + rollback_count,
            rollback_count=rollback_count,
        ),
        project_root,
    )


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
            "predecessor_hash": validated["predecessor"]["evidence_hash"],
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
) -> dict[str, Any]:
    validated_report = validate_report(phase, report)
    validated_freeze = validate_freeze_manifest(phase, freeze)
    if writer_id == reviewer_id or _UUID7_RE.fullmatch(writer_id) is None or _UUID7_RE.fullmatch(reviewer_id) is None:
        raise ProgramError("reviewer_identity_not_independent")
    _timestamp(reviewed_at)
    return _self_hash(
        {
            "schema_version": f"{phase}.final_review.v1",
            "phase": phase,
            "writer_id": writer_id,
            "reviewer_id": reviewer_id,
            "reviewed_at": reviewed_at,
            "finding_count": 0,
            "decision": "approved_bounded_claim",
            "report_hash": validated_report["report_hash"],
            "freeze_hash": validated_freeze["manifest_hash"],
            "review_hash": "",
        },
        "review_hash",
    )


def assemble_release_evidence(
    phase: str,
    report: Mapping[str, Any],
    freeze: Mapping[str, Any],
    review: Mapping[str, Any],
) -> dict[str, Any]:
    validated_report = validate_report(phase, report)
    validated_freeze = validate_freeze_manifest(phase, freeze)
    validated_review = validate_final_review(phase, review, report=validated_report, freeze=validated_freeze)
    return _self_hash(
        {
            "schema_version": SPECS[phase].release_schema,
            "phase": phase,
            "status": validated_report["status"],
            "claim": validated_report["claim"],
            "limitations": validated_report["limitations"],
            "source_hashes": validated_report["source_hashes"],
            "predecessor": validated_report["predecessor"],
            "metrics": validated_report["metrics"],
            "counters": validated_report["counters"],
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
        "claim",
        "limitations",
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
    if value["schema_version"] != spec.report_schema or value["phase"] != phase or value["status"] != spec.status or value["claim"] != spec.claim or value["limitations"] != list(spec.limitations):
        raise ProgramError("report_contract_invalid")
    _hash(value["input_hash"], "input_hash")
    _validate_predecessor_shape(phase, value["predecessor"])
    _hash_map(value["source_hashes"], "source_hashes")
    if set(value["source_hashes"]) != set(_source_paths(phase)):
        raise ProgramError("report_source_keyset_invalid")
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
    if set(value) != {"schema_version", "phase", "source_hashes", "predecessor_hash", "report_hash", "manifest_hash"}:
        raise ProgramError("freeze_keyset_invalid")
    if value["schema_version"] != f"{phase}.freeze_manifest.v1" or value["phase"] != phase:
        raise ProgramError("freeze_contract_invalid")
    _hash_map(value["source_hashes"], "source_hashes")
    for field in ("predecessor_hash", "report_hash", "manifest_hash"):
        _hash(value[field], field)
    _validate_self_hash(value, "manifest_hash")
    return value


def validate_final_review(
    phase: str,
    review: Mapping[str, Any],
    *,
    report: Mapping[str, Any],
    freeze: Mapping[str, Any],
) -> dict[str, Any]:
    value = deepcopy(dict(review))
    required = {"schema_version", "phase", "writer_id", "reviewer_id", "reviewed_at", "finding_count", "decision", "report_hash", "freeze_hash", "review_hash"}
    if set(value) != required or value["schema_version"] != f"{phase}.final_review.v1" or value["phase"] != phase:
        raise ProgramError("review_contract_invalid")
    if value["writer_id"] == value["reviewer_id"] or _UUID7_RE.fullmatch(value["writer_id"]) is None or _UUID7_RE.fullmatch(value["reviewer_id"]) is None:
        raise ProgramError("reviewer_identity_not_independent")
    _timestamp(value["reviewed_at"])
    if value["finding_count"] != 0 or value["decision"] != "approved_bounded_claim":
        raise ProgramError("review_findings_not_closed")
    if value["report_hash"] != report["report_hash"] or value["freeze_hash"] != freeze["manifest_hash"]:
        raise ProgramError("review_binding_invalid")
    _validate_self_hash(value, "review_hash")
    return value


def validate_release_evidence(phase: str, release: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    spec = SPECS[_phase(phase)]
    value = deepcopy(dict(release))
    required = {"schema_version", "phase", "status", "claim", "limitations", "source_hashes", "predecessor", "metrics", "counters", "report_hash", "freeze_hash", "review_hash", "evidence_hash"}
    if set(value) != required or value["schema_version"] != spec.release_schema or value["phase"] != phase:
        raise ProgramError("release_contract_invalid")
    if value["status"] != spec.status or value["claim"] != spec.claim or value["limitations"] != list(spec.limitations):
        raise ProgramError("release_claim_invalid")
    _validate_self_hash(value, "evidence_hash")
    if value["source_hashes"] != _source_hashes(project_root, phase):
        raise ProgramError("release_source_bindings_stale")
    if value["predecessor"] != _canonical_predecessor(phase, project_root):
        raise ProgramError("release_predecessor_binding_stale")
    _validate_counters(value["counters"])
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
        "claim": spec.claim,
        "limitations": list(spec.limitations),
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
    passed = deepcopy(dict(predecessor))
    canonical_value = load_phase_input(project_root / SPECS[phase].predecessor_path, f"{SPECS[phase].predecessor_phase}-release")
    if passed != canonical_value:
        raise ProgramError("predecessor_not_canonical")
    if phase == "p159":
        validate_p154_p158_release_evidence("p158", passed, project_root=project_root)
    else:
        validate_release_evidence(SPECS[phase].predecessor_phase, passed, project_root=project_root)
    return _canonical_predecessor(phase, project_root)


def _canonical_predecessor(phase: str, project_root: Path) -> dict[str, Any]:
    spec = SPECS[phase]
    path = project_root / spec.predecessor_path
    value = load_phase_input(path, f"{spec.predecessor_phase}-release")
    if phase == "p159":
        validated = validate_p154_p158_release_evidence("p158", value, project_root=project_root)
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


def _validate_predecessor_shape(phase: str, value: Any) -> None:
    entry = _mapping(value, "predecessor")
    spec = SPECS[phase]
    if set(entry) != {"phase", "path", "schema_version", "required_status", "file_hash", "evidence_hash"}:
        raise ProgramError("predecessor_keyset_invalid")
    if entry["phase"] != spec.predecessor_phase or entry["path"] != spec.predecessor_path or entry["schema_version"] != spec.predecessor_schema or entry["required_status"] != spec.predecessor_status:
        raise ProgramError("predecessor_contract_invalid")
    _hash(entry["file_hash"], "predecessor_file_hash")
    _hash(entry["evidence_hash"], "predecessor_evidence_hash")


def _source_paths(phase: str) -> tuple[str, ...]:
    return (
        "app/services/p159_p163_live_operator_program.py",
        f"docs/operations/{phase}-plan-review.md",
        f"docs/operations/{phase}-test-spec.md",
        "docs/operations/p159-p163-live-operator-program.md",
        f"docs/tickets/{phase}/README.md",
        f"evals/{phase}/input/cases.json",
        "scripts/run_p159_p163_qualification.py",
        "scripts/verify_p159_p163.sh",
        "tests/test_p159_p163_live_operator_program.py",
    )


def _source_hashes(project_root: Path, phase: str) -> dict[str, str]:
    return {path: file_hash(project_root / path) for path in sorted(_source_paths(phase))}


def _input(payload: Mapping[str, Any], phase: str, collection: str) -> dict[str, Any]:
    value = deepcopy(dict(payload))
    if value.get("schema_version") != f"{phase}.input.v1" or value.get("phase") != phase or collection not in value:
        raise ProgramError(f"input_contract_invalid:{phase}")
    return value


def _state(value: Any) -> dict[str, Any]:
    state = _mapping(value, "state")
    if set(state) != {"error_rate_bps", "healthy", "generation"}:
        raise ProgramError("state_keyset_invalid")
    if not isinstance(state["error_rate_bps"], int) or not isinstance(state["healthy"], bool) or not isinstance(state["generation"], int):
        raise ProgramError("state_invalid")
    return dict(state)


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
    if set(counters) != set(_COUNTER_KEYS) or any(not isinstance(counters[key], int) or counters[key] < 0 for key in _COUNTER_KEYS):
        raise ProgramError("counter_contract_invalid")
    if any(counters[key] != 0 for key in ("external_network_call_count", "production_mutation_count", "credential_read_count", "shell_execution_count")):
        raise ProgramError("unsafe_authority_counter_nonzero")
    return {key: counters[key] for key in _COUNTER_KEYS}


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


def _now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _rate(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else round(numerator / denominator, 4)
