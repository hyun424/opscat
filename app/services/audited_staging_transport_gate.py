"""P64 audited staging credential and transport gate.

This gate sits between P63 preflight eligibility and any network-capable staging
transport. Normal verification uses dry-run mode and injected mock secrets only;
it does not read .env or call real provider APIs.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.services.redaction import REDACTED, redact_value
from app.services.staging_live_read_only_preflight import run_staging_live_read_only_preflight_fixture

_BOUNDARY_BASE: dict[str, bool] = {
    "audited_transport_gate": True,
    "read_only_get_only": True,
    "real_network_required_for_tests": False,
    "reads_dotenv": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "action_execution_enabled": False,
    "unattended_production_operation_claimed": False,
}
_SAFE_CREDENTIAL_PREFIXES = ("env:", "secret:", "vault:")
_REMOTE_PREFIXES = ("http://", "https://", "s3://", "gs://", "az://", "ftp://")
_MAX_TIMEOUT_MS = 5_000


@dataclass(frozen=True)
class AuditedStagingRequest:
    id: str
    preflight_check_id: str
    connector_id: str
    credential_ref: str
    method: str
    url: str
    timeout_ms: int
    expected_status: int
    mock_status: int

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AuditedStagingRequest:
        return cls(
            id=str(data.get("id", "audited-staging-request")),
            preflight_check_id=str(data.get("preflight_check_id", "")),
            connector_id=str(data.get("connector_id", "")),
            credential_ref=str(data.get("credential_ref", "")),
            method=str(data.get("method", "GET")).upper(),
            url=str(data.get("url", "")),
            timeout_ms=int(data.get("timeout_ms", 1_000) or 1_000),
            expected_status=int(data.get("expected_status", 200) or 200),
            mock_status=int(data.get("mock_status", 200) or 200),
        )

    @property
    def host(self) -> str:
        return str(urlparse(self.url).hostname or "")


@dataclass(frozen=True)
class AuditedStagingTransportPlan:
    preflight_manifest: Path
    approval_id: str
    allowed_hosts: tuple[str, ...]
    mock_secret_store: Mapping[str, str]
    requests: tuple[AuditedStagingRequest, ...]


@dataclass(frozen=True)
class AuditedTransportResponse:
    status_code: int
    elapsed_ms: int


@dataclass
class MockAuditedStagingTransport:
    calls: list[dict[str, Any]] = field(default_factory=list)

    def get(self, request: AuditedStagingRequest, credential: str) -> AuditedTransportResponse:
        self.calls.append(
            {
                "request_id": request.id,
                "method": "GET",
                "host": request.host,
                "timeout_ms": request.timeout_ms,
                "authorization_present": bool(credential),
            }
        )
        return AuditedTransportResponse(status_code=request.mock_status, elapsed_ms=min(request.timeout_ms, 50))


@dataclass(frozen=True)
class AuditLedgerEntry:
    request_id: str
    connector_id: str
    decision: str
    reasons: tuple[str, ...]
    method: str
    host: str
    approval_id: str
    credential_ref_fingerprint: str
    credential_resolved: bool
    redaction_applied: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "connector_id": self.connector_id,
            "decision": self.decision,
            "reasons": list(self.reasons),
            "method": self.method,
            "host": self.host,
            "approval_id": self.approval_id,
            "credential_ref_fingerprint": self.credential_ref_fingerprint,
            "credential_resolved": self.credential_resolved,
            "redaction_applied": self.redaction_applied,
        }


@dataclass(frozen=True)
class AuditedStagingTransportGateResult:
    request: AuditedStagingRequest
    status: str
    reasons: tuple[str, ...]
    p63_preflight_eligible: bool
    credential_resolved: bool
    approval_present: bool
    allowlisted_host: bool
    response_status: int | None = None
    elapsed_ms: int | None = None

    @property
    def approved(self) -> bool:
        return not self.reasons

    @property
    def attempted(self) -> bool:
        return self.status in {"successful", "failed"}

    def audit_entry(self, approval_id: str) -> AuditLedgerEntry:
        return AuditLedgerEntry(
            request_id=self.request.id,
            connector_id=self.request.connector_id,
            decision=self.status,
            reasons=self.reasons,
            method=self.request.method,
            host=self.request.host,
            approval_id=approval_id if self.approval_present else "",
            credential_ref_fingerprint=_fingerprint(self.request.credential_ref),
            credential_resolved=self.credential_resolved,
            redaction_applied=True,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "request_id": self.request.id,
            "preflight_check_id": self.request.preflight_check_id,
            "connector_id": self.request.connector_id,
            "method": self.request.method,
            "url_host": self.request.host,
            "timeout_ms": self.request.timeout_ms,
            "expected_status": self.request.expected_status,
            "credential_ref": REDACTED if _is_raw_credential(self.request.credential_ref) else self.request.credential_ref,
            "credential_ref_fingerprint": _fingerprint(self.request.credential_ref),
            "status": self.status,
            "reasons": list(self.reasons),
            "p63_preflight_eligible": self.p63_preflight_eligible,
            "credential_resolved": self.credential_resolved,
            "approval_present": self.approval_present,
            "allowlisted_host": self.allowlisted_host,
            "response_status": self.response_status,
            "elapsed_ms": self.elapsed_ms,
            "transport_called": self.attempted,
            "live_api_called": self.attempted,
            "production_mutation_count": 0,
            "action_execution_count": 0,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class AuditedStagingTransportGateReport:
    plan: AuditedStagingTransportPlan
    results: tuple[AuditedStagingTransportGateResult, ...]
    live_staging: bool
    manual_approval: bool
    transport_call_count: int

    def to_dict(self) -> dict[str, Any]:
        approved = tuple(result for result in self.results if result.approved)
        attempted = tuple(result for result in self.results if result.attempted)
        successful = tuple(result for result in self.results if result.status == "successful")
        blocked = tuple(result for result in self.results if result.status == "blocked")
        raw_secret_blocked = tuple(result for result in self.results if "raw_credential_value" in result.reasons)
        missing_approval = tuple(result for result in self.results if "manual_approval_missing" in result.reasons)
        audit_entries = [result.audit_entry(self.plan.approval_id).to_dict() for result in self.results]
        payload = {
            "summary": {
                "request_count": len(self.results),
                "approved_request_count": len(approved),
                "attempted_request_count": len(attempted),
                "successful_request_count": len(successful),
                "blocked_request_count": len(blocked),
                "audit_entry_count": len(audit_entries),
                "passed": _passed(self.live_staging, approved, attempted, successful, audit_entries),
            },
            "score": {
                "transport_call_count": self.transport_call_count,
                "live_api_call_count": len(attempted),
                "raw_secret_block_count": len(raw_secret_blocked),
                "missing_approval_count": len(missing_approval),
                "production_mutation_count": 0,
                "action_execution_count": 0,
            },
            "boundary": {
                **_BOUNDARY_BASE,
                "default_dry_run": not self.live_staging,
                "live_staging_enabled": self.live_staging,
            },
            "operator_handoff": _operator_handoff(self.live_staging, self.manual_approval, approved, blocked),
            "requests": [result.to_dict() for result in self.results],
            "audit_ledger": audit_entries,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def load_audited_staging_transport_gate_plan(path: str | Path) -> AuditedStagingTransportPlan:
    local_path = _ensure_local_path(path)
    data = json.loads(local_path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("audited staging transport gate manifest must be an object")
    requests = tuple(AuditedStagingRequest.from_dict(item) for item in _sequence(data.get("requests", ())) if isinstance(item, Mapping))
    secret_store = {str(key): str(value) for key, value in _mapping(data.get("mock_secret_store")).items()}
    return AuditedStagingTransportPlan(
        preflight_manifest=Path(str(data.get("preflight_manifest", "evals/staging/p63_staging_live_preflight.json"))),
        approval_id=str(data.get("approval_id", "")),
        allowed_hosts=tuple(str(item) for item in _sequence(data.get("allowed_hosts", ()))),
        mock_secret_store=secret_store,
        requests=requests,
    )


def run_audited_staging_transport_gate_fixture(
    path: str | Path,
    *,
    live_staging: bool = False,
    manual_approval: bool = False,
    transport: MockAuditedStagingTransport | None = None,
) -> AuditedStagingTransportGateReport:
    plan = load_audited_staging_transport_gate_plan(path)
    preflight_payload = run_staging_live_read_only_preflight_fixture(plan.preflight_manifest).to_dict()
    preflight_by_id = {
        str(item.get("check_id")): item
        for item in _sequence(preflight_payload.get("checks", ()))
        if isinstance(item, Mapping)
    }
    results = tuple(_evaluate_request(request, preflight_by_id.get(request.preflight_check_id, {}), plan, live_staging, manual_approval, transport) for request in plan.requests)
    return AuditedStagingTransportGateReport(
        plan=plan,
        results=results,
        live_staging=live_staging,
        manual_approval=manual_approval,
        transport_call_count=len(transport.calls) if transport is not None else 0,
    )


def render_audited_staging_transport_gate_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("score"))
    boundary = _mapping(payload.get("boundary"))
    handoff = _mapping(payload.get("operator_handoff"))
    lines = [
        "# OpsCat Audited Staging Credential + Transport Gate",
        "",
        "Dry-run mode records audited decisions without transport calls. "
        "Live staging requires approval, indirect credentials, HTTPS GET, allowlisted host, P63 eligibility, and mock/approved transport.",
        "",
        "## Summary",
        f"- Requests: {summary.get('request_count')}",
        f"- Approved requests: {summary.get('approved_request_count')}",
        f"- Attempted requests: {summary.get('attempted_request_count')}",
        f"- Successful requests: {summary.get('successful_request_count')}",
        f"- Blocked requests: {summary.get('blocked_request_count')}",
        f"- Audit entries: {summary.get('audit_entry_count')}",
        "",
        "## Safety counters",
        f"- transport_call_count: {score.get('transport_call_count')}",
        f"- live_api_call_count: {score.get('live_api_call_count')}",
        f"- raw_secret_block_count: {score.get('raw_secret_block_count')}",
        f"- missing_approval_count: {score.get('missing_approval_count')}",
        f"- production_mutation_count: {score.get('production_mutation_count')}",
        f"- action_execution_count: {score.get('action_execution_count')}",
        "",
        "## Boundary",
        f"- default_dry_run: {boundary.get('default_dry_run')}",
        f"- live_staging_enabled: {boundary.get('live_staging_enabled')}",
        "",
        "## Operator handoff",
        f"- Next step: {handoff.get('next_step')}",
        "",
        "## Requests",
    ]
    for item in _sequence(payload.get("requests", ())):
        if isinstance(item, Mapping):
            reasons = ",".join(str(reason) for reason in _sequence(item.get("reasons", ())))
            lines.append(f"- `{item.get('request_id')}` connector={item.get('connector_id')} status={item.get('status')} reasons={reasons}")
    lines.extend(["", "## Audit ledger"])
    for item in _sequence(payload.get("audit_ledger", ())):
        if isinstance(item, Mapping):
            lines.append(f"- `{item.get('request_id')}` decision={item.get('decision')} host={item.get('host')} redaction={item.get('redaction_applied')}")
    return "\n".join(lines) + "\n"


def write_audited_staging_transport_gate_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_audited_staging_transport_gate_markdown(payload), encoding="utf-8")


def _evaluate_request(
    request: AuditedStagingRequest,
    preflight: Mapping[str, Any],
    plan: AuditedStagingTransportPlan,
    live_staging: bool,
    manual_approval: bool,
    transport: MockAuditedStagingTransport | None,
) -> AuditedStagingTransportGateResult:
    p63_eligible = bool(preflight.get("eligible"))
    allowlisted_host = request.host in set(plan.allowed_hosts)
    credential = _resolve_credential(request.credential_ref, plan.mock_secret_store)
    reasons = list(_base_reasons(request, p63_eligible, allowlisted_host, credential is not None))

    if reasons:
        return AuditedStagingTransportGateResult(
            request=request,
            status="blocked",
            reasons=tuple(reasons),
            p63_preflight_eligible=p63_eligible,
            credential_resolved=credential is not None,
            approval_present=manual_approval,
            allowlisted_host=allowlisted_host,
        )
    if not live_staging:
        return AuditedStagingTransportGateResult(
            request=request,
            status="approved_dry_run",
            reasons=(),
            p63_preflight_eligible=p63_eligible,
            credential_resolved=True,
            approval_present=manual_approval,
            allowlisted_host=allowlisted_host,
        )
    if not manual_approval or not plan.approval_id:
        return AuditedStagingTransportGateResult(
            request=request,
            status="blocked",
            reasons=("manual_approval_missing",),
            p63_preflight_eligible=p63_eligible,
            credential_resolved=True,
            approval_present=False,
            allowlisted_host=allowlisted_host,
        )
    if transport is None:
        return AuditedStagingTransportGateResult(
            request=request,
            status="blocked",
            reasons=("safe_transport_missing",),
            p63_preflight_eligible=p63_eligible,
            credential_resolved=True,
            approval_present=True,
            allowlisted_host=allowlisted_host,
        )
    response = transport.get(request, credential or "")
    status = "successful" if response.status_code == request.expected_status else "failed"
    return AuditedStagingTransportGateResult(
        request=request,
        status=status,
        reasons=() if status == "successful" else ("unexpected_status_code",),
        p63_preflight_eligible=p63_eligible,
        credential_resolved=True,
        approval_present=True,
        allowlisted_host=allowlisted_host,
        response_status=response.status_code,
        elapsed_ms=response.elapsed_ms,
    )


def _base_reasons(request: AuditedStagingRequest, p63_eligible: bool, allowlisted_host: bool, credential_resolved: bool) -> tuple[str, ...]:
    reasons: list[str] = []
    if not p63_eligible:
        reasons.append("p63_preflight_not_eligible")
    if _is_raw_credential(request.credential_ref):
        reasons.append("raw_credential_value")
    if not credential_resolved:
        reasons.append("credential_ref_unresolved")
    if request.method != "GET":
        reasons.append("non_get_method")
    if not allowlisted_host:
        reasons.append("host_not_allowlisted")
    if not request.url.lower().startswith("https://"):
        reasons.append("non_https_url")
    if request.timeout_ms <= 0 or request.timeout_ms > _MAX_TIMEOUT_MS:
        reasons.append("unsafe_timeout_budget")
    return tuple(reasons)


def _operator_handoff(
    live_staging: bool,
    manual_approval: bool,
    approved: Sequence[AuditedStagingTransportGateResult],
    blocked: Sequence[AuditedStagingTransportGateResult],
) -> dict[str, Any]:
    if not live_staging:
        next_step = "rerun with explicit live staging flag, manual approval, and audited transport"
    elif not manual_approval:
        next_step = "collect manual approval ID before audited staging transport"
    else:
        next_step = "review audit ledger and successful staging GETs before enabling polling"
    return {
        "approved_requests": [result.request.id for result in approved],
        "blocked_requests": [result.request.id for result in blocked],
        "next_step": next_step,
    }


def _passed(
    live_staging: bool,
    approved: Sequence[AuditedStagingTransportGateResult],
    attempted: Sequence[AuditedStagingTransportGateResult],
    successful: Sequence[AuditedStagingTransportGateResult],
    audit_entries: Sequence[Mapping[str, Any]],
) -> bool:
    if len(audit_entries) < len(approved):
        return False
    if not live_staging:
        return len(approved) >= 3 and len(attempted) == 0
    return len(approved) >= 3 and len(successful) == len(attempted)


def _resolve_credential(credential_ref: str, secret_store: Mapping[str, str]) -> str | None:
    if _is_raw_credential(credential_ref):
        return None
    if not credential_ref.lower().startswith(_SAFE_CREDENTIAL_PREFIXES):
        return None
    return secret_store.get(credential_ref)


def _is_raw_credential(value: str) -> bool:
    lowered = value.lower()
    return bool(value) and not lowered.startswith(_SAFE_CREDENTIAL_PREFIXES)


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _ensure_local_path(path: str | Path) -> Path:
    value = str(path)
    if value.lower().startswith(_REMOTE_PREFIXES):
        raise ValueError("remote audited staging transport manifests are not allowed for normal verification")
    local_path = Path(value)
    if not local_path.exists():
        raise FileNotFoundError(f"audited staging transport manifest does not exist: {local_path}")
    return local_path


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()
