"""P65 real staging read-only dry attach.

This module creates a real-staging-shaped attachment plan without reading .env,
without resolving real secret values, and without opening network connections.
It requires P64 audit handoff before marking an attachment attach-ready.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.services.audited_staging_transport_gate import run_audited_staging_transport_gate_fixture
from app.services.redaction import REDACTED, redact_value

_BOUNDARY: dict[str, bool] = {
    "dry_attach_only": True,
    "real_staging_shape": True,
    "secret_provider_contract_only": True,
    "reads_dotenv": False,
    "real_credential_reads_enabled": False,
    "real_network_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "action_execution_enabled": False,
    "unattended_production_operation_claimed": False,
}
_SAFE_SECRET_PREFIXES = ("provider://", "secret://", "vault://")
_REMOTE_PREFIXES = ("http://", "https://", "s3://", "gs://", "az://", "ftp://")
_MAX_TIMEOUT_MS = 5_000


@dataclass(frozen=True)
class SecretProviderContract:
    kind: str
    namespace: str
    refs: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SecretProviderContract:
        return cls(
            kind=str(data.get("kind", "mock-provider")),
            namespace=str(data.get("namespace", "")),
            refs=tuple(str(item) for item in _sequence(data.get("refs", ()))),
        )

    def has_ref(self, credential_ref: str) -> bool:
        return credential_ref in self.refs

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "namespace": self.namespace,
            "ref_count": len(self.refs),
            "ref_fingerprints": [_fingerprint(ref) for ref in self.refs],
        }


@dataclass(frozen=True)
class RealStagingAttachment:
    id: str
    provider: str
    connector_id: str
    audit_request_id: str
    environment: str
    endpoint: str
    credential_ref: str
    health_probe_path: str
    method: str
    timeout_ms: int
    polling_enabled_after_attach: bool

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RealStagingAttachment:
        return cls(
            id=str(data.get("id", "real-staging-attachment")),
            provider=str(data.get("provider", "unknown")).lower(),
            connector_id=str(data.get("connector_id", "")),
            audit_request_id=str(data.get("audit_request_id", "")),
            environment=str(data.get("environment", "unknown")).lower(),
            endpoint=str(data.get("endpoint", "")),
            credential_ref=str(data.get("credential_ref", "")),
            health_probe_path=str(data.get("health_probe_path", "/")),
            method=str(data.get("method", "GET")).upper(),
            timeout_ms=int(data.get("timeout_ms", 1_000) or 1_000),
            polling_enabled_after_attach=bool(data.get("polling_enabled_after_attach", False)),
        )

    @property
    def host(self) -> str:
        return str(urlparse(self.endpoint).hostname or "")


@dataclass(frozen=True)
class DetachPlan:
    attachment_id: str
    safe_to_disable_polling: bool
    provider_mutation_required: bool
    steps: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "attachment_id": self.attachment_id,
            "safe_to_disable_polling": self.safe_to_disable_polling,
            "provider_mutation_required": self.provider_mutation_required,
            "steps": list(self.steps),
        }


@dataclass(frozen=True)
class RealStagingDryAttachResult:
    attachment: RealStagingAttachment
    status: str
    reasons: tuple[str, ...]
    audit_handoff: Mapping[str, Any]
    allowlisted_host: bool
    secret_provider_ref_valid: bool
    detach_plan: DetachPlan | None

    @property
    def attach_ready(self) -> bool:
        return self.status == "attach_ready_dry_run"

    def to_dict(self) -> dict[str, Any]:
        credential_ref = REDACTED if _is_raw_credential(self.attachment.credential_ref) else REDACTED
        payload = {
            "attachment_id": self.attachment.id,
            "provider": self.attachment.provider,
            "connector_id": self.attachment.connector_id,
            "audit_request_id": self.attachment.audit_request_id,
            "environment": self.attachment.environment,
            "endpoint_host": self.attachment.host,
            "health_probe_path": self.attachment.health_probe_path,
            "method": self.attachment.method,
            "timeout_ms": self.attachment.timeout_ms,
            "credential_ref": credential_ref,
            "credential_ref_fingerprint": _fingerprint(self.attachment.credential_ref),
            "status": self.status,
            "reasons": list(self.reasons),
            "allowlisted_host": self.allowlisted_host,
            "secret_provider_ref_valid": self.secret_provider_ref_valid,
            "audit_handoff": dict(self.audit_handoff),
            "detach_plan": self.detach_plan.to_dict() if self.detach_plan is not None else None,
            "env_read_count": 0,
            "real_credential_read_count": 0,
            "network_call_count": 0,
            "production_mutation_count": 0,
            "action_execution_count": 0,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class RealStagingDryAttachPlan:
    audit_gate_manifest: Path
    allowed_hosts: tuple[str, ...]
    secret_provider: SecretProviderContract
    attachments: tuple[RealStagingAttachment, ...]


@dataclass(frozen=True)
class RealStagingDryAttachReport:
    plan: RealStagingDryAttachPlan
    results: tuple[RealStagingDryAttachResult, ...]

    def to_dict(self) -> dict[str, Any]:
        attach_ready = tuple(result for result in self.results if result.attach_ready)
        blocked = tuple(result for result in self.results if result.status == "blocked")
        detach_plans = tuple(result for result in attach_ready if result.detach_plan is not None)
        audit_handoffs = tuple(result for result in attach_ready if result.audit_handoff)
        raw_secret_blocked = tuple(result for result in self.results if "raw_credential_value" in result.reasons)
        payload = {
            "summary": {
                "attachment_count": len(self.results),
                "attach_ready_count": len(attach_ready),
                "blocked_count": len(blocked),
                "detach_plan_count": len(detach_plans),
                "audit_handoff_count": len(audit_handoffs),
                "passed": len(attach_ready) >= 3 and len(blocked) >= 1 and len(detach_plans) == len(attach_ready),
            },
            "score": {
                "env_read_count": 0,
                "real_credential_read_count": 0,
                "network_call_count": 0,
                "raw_secret_block_count": len(raw_secret_blocked),
                "production_mutation_count": 0,
                "action_execution_count": 0,
            },
            "boundary": dict(_BOUNDARY),
            "secret_provider": self.plan.secret_provider.to_dict(),
            "operator_handoff": _operator_handoff(attach_ready, blocked),
            "attachments": [result.to_dict() for result in self.results],
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def load_real_staging_dry_attach_plan(path: str | Path) -> RealStagingDryAttachPlan:
    local_path = _ensure_local_path(path)
    data = json.loads(local_path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("real staging dry attach manifest must be an object")
    attachments = tuple(RealStagingAttachment.from_dict(item) for item in _sequence(data.get("attachments", ())) if isinstance(item, Mapping))
    return RealStagingDryAttachPlan(
        audit_gate_manifest=Path(str(data.get("audit_gate_manifest", "evals/staging/p64_audited_credential_transport_gate.json"))),
        allowed_hosts=tuple(str(item) for item in _sequence(data.get("allowed_hosts", ()))),
        secret_provider=SecretProviderContract.from_dict(_mapping(data.get("secret_provider"))),
        attachments=attachments,
    )


def run_real_staging_dry_attach_fixture(path: str | Path) -> RealStagingDryAttachReport:
    plan = load_real_staging_dry_attach_plan(path)
    audit_payload = run_audited_staging_transport_gate_fixture(plan.audit_gate_manifest).to_dict()
    audit_by_request = {
        str(item.get("request_id")): item
        for item in _sequence(audit_payload.get("requests", ()))
        if isinstance(item, Mapping)
    }
    results = tuple(_evaluate_attachment(attachment, plan, audit_by_request.get(attachment.audit_request_id, {})) for attachment in plan.attachments)
    return RealStagingDryAttachReport(plan=plan, results=results)


def render_real_staging_dry_attach_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("score"))
    handoff = _mapping(payload.get("operator_handoff"))
    lines = [
        "# OpsCat Real Staging Read-only Dry Attach",
        "",
        "Builds a real-staging-shaped attachment plan without reading .env, resolving real credentials, or making network calls.",
        "",
        "## Summary",
        f"- Attachments: {summary.get('attachment_count')}",
        f"- Attach ready: {summary.get('attach_ready_count')}",
        f"- Blocked: {summary.get('blocked_count')}",
        f"- Detach plans: {summary.get('detach_plan_count')}",
        f"- Audit handoffs: {summary.get('audit_handoff_count')}",
        "",
        "## Safety counters",
        f"- env_read_count: {score.get('env_read_count')}",
        f"- real_credential_read_count: {score.get('real_credential_read_count')}",
        f"- network_call_count: {score.get('network_call_count')}",
        f"- production_mutation_count: {score.get('production_mutation_count')}",
        f"- action_execution_count: {score.get('action_execution_count')}",
        "",
        "## Operator handoff",
        f"- Next step: {handoff.get('next_step')}",
        "",
        "## Attachments",
    ]
    for item in _sequence(payload.get("attachments", ())):
        if isinstance(item, Mapping):
            reasons = ",".join(str(reason) for reason in _sequence(item.get("reasons", ())))
            lines.append(f"- `{item.get('attachment_id')}` provider={item.get('provider')} status={item.get('status')} reasons={reasons}")
    lines.extend(["", "## Detach plan"])
    for item in _sequence(payload.get("attachments", ())):
        if isinstance(item, Mapping) and isinstance(item.get("detach_plan"), Mapping):
            plan = _mapping(item.get("detach_plan"))
            lines.append(f"- `{item.get('attachment_id')}` safe_to_disable_polling={plan.get('safe_to_disable_polling')} provider_mutation_required={plan.get('provider_mutation_required')}")
    return "\n".join(lines) + "\n"


def write_real_staging_dry_attach_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_real_staging_dry_attach_markdown(payload), encoding="utf-8")


def _evaluate_attachment(attachment: RealStagingAttachment, plan: RealStagingDryAttachPlan, audit: Mapping[str, Any]) -> RealStagingDryAttachResult:
    allowlisted_host = attachment.host in set(plan.allowed_hosts)
    secret_provider_ref_valid = _is_provider_ref(attachment.credential_ref) and plan.secret_provider.has_ref(attachment.credential_ref)
    reasons = list(_base_reasons(attachment, allowlisted_host, secret_provider_ref_valid, audit))
    if reasons:
        return RealStagingDryAttachResult(
            attachment=attachment,
            status="blocked",
            reasons=tuple(reasons),
            audit_handoff=_audit_handoff(audit),
            allowlisted_host=allowlisted_host,
            secret_provider_ref_valid=secret_provider_ref_valid,
            detach_plan=None,
        )
    return RealStagingDryAttachResult(
        attachment=attachment,
        status="attach_ready_dry_run",
        reasons=(),
        audit_handoff=_audit_handoff(audit),
        allowlisted_host=allowlisted_host,
        secret_provider_ref_valid=secret_provider_ref_valid,
        detach_plan=_detach_plan(attachment),
    )


def _base_reasons(
    attachment: RealStagingAttachment,
    allowlisted_host: bool,
    secret_provider_ref_valid: bool,
    audit: Mapping[str, Any],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if attachment.environment != "staging":
        reasons.append("non_staging_environment")
    if not attachment.endpoint.lower().startswith("https://"):
        reasons.append("non_https_endpoint")
    if not allowlisted_host:
        reasons.append("host_not_allowlisted")
    if _is_raw_credential(attachment.credential_ref):
        reasons.append("raw_credential_value")
    elif not secret_provider_ref_valid:
        reasons.append("secret_provider_ref_missing")
    if str(audit.get("status")) != "approved_dry_run":
        reasons.append("audit_handoff_not_approved")
    if attachment.method != "GET":
        reasons.append("non_get_method")
    if attachment.timeout_ms <= 0 or attachment.timeout_ms > _MAX_TIMEOUT_MS:
        reasons.append("unsafe_timeout_budget")
    if attachment.polling_enabled_after_attach:
        reasons.append("polling_enabled_before_attach")
    return tuple(reasons)


def _audit_handoff(audit: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "p64_request_id": str(audit.get("request_id", "")),
        "p64_decision": str(audit.get("status", "missing")),
        "credential_ref_fingerprint": str(audit.get("credential_ref_fingerprint", "")),
        "transport_called": bool(audit.get("transport_called", False)),
        "live_api_called": bool(audit.get("live_api_called", False)),
    }


def _detach_plan(attachment: RealStagingAttachment) -> DetachPlan:
    return DetachPlan(
        attachment_id=attachment.id,
        safe_to_disable_polling=True,
        provider_mutation_required=False,
        steps=(
            "disable local polling schedule",
            "clear local attachment state",
            "retain audit ledger evidence",
            "do not mutate provider configuration",
        ),
    )


def _operator_handoff(attach_ready: Sequence[RealStagingDryAttachResult], blocked: Sequence[RealStagingDryAttachResult]) -> dict[str, Any]:
    return {
        "attach_ready": [result.attachment.id for result in attach_ready],
        "blocked": [result.attachment.id for result in blocked],
        "next_step": "collect explicit live attach approval before resolving real staging credentials",
    }


def _is_provider_ref(value: str) -> bool:
    lowered = value.lower()
    return any(lowered.startswith(prefix) for prefix in _SAFE_SECRET_PREFIXES)


def _is_raw_credential(value: str) -> bool:
    return bool(value) and not _is_provider_ref(value)


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _ensure_local_path(path: str | Path) -> Path:
    value = str(path)
    if value.lower().startswith(_REMOTE_PREFIXES):
        raise ValueError("remote real staging dry attach manifests are not allowed for normal verification")
    local_path = Path(value)
    if not local_path.exists():
        raise FileNotFoundError(f"real staging dry attach manifest does not exist: {local_path}")
    return local_path


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()
