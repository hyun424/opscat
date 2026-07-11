"""P62 staging read-only connector contract.

This module validates provider-shaped staging observability connector manifests
without opening network connections. It is the contract gate before real staging
credentials or provider APIs are attached.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.redaction import REDACTED, redact_value

_BOUNDARY: dict[str, bool] = {
    "offline_manifest_only": True,
    "staging_contract_only": True,
    "read_only_connector": True,
    "live_api_calls_enabled": False,
    "auth_session_work_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "action_execution_enabled": False,
    "unattended_production_operation_claimed": False,
}
_REQUIRED_PROVIDERS = ("grafana", "sentry", "datadog")
_PROVIDER_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "grafana": ("series",),
    "sentry": ("events",),
    "datadog": ("monitors", "logs"),
}
_WRITE_SCOPE_MARKERS = ("write", "admin", "delete", "manage", "execute", "mutation", "mute", "restart", "deploy", "rollback")
_MUTATION_OPERATION_MARKERS = ("write", "admin", "delete", "manage", "execute", "mutation", "mute", "restart", "deploy", "rollback", "patch", "create")
_REMOTE_PREFIXES = ("http://", "https://", "s3://", "gs://", "az://", "ftp://")
_SAFE_ENDPOINT_PREFIXES = ("env:", "secret:", "vault:", "config:")
_SAFE_CREDENTIAL_PREFIXES = ("env:", "secret:", "vault:")
_MAX_TIMEOUT_MS = 5_000
_MAX_RATE_LIMIT_PER_MINUTE = 60


@dataclass(frozen=True)
class StagingQueryPlan:
    id: str
    kind: str
    query_ref: str
    timeout_ms: int
    rate_limit_per_minute: int

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, index: int) -> StagingQueryPlan:
        return cls(
            id=str(data.get("id", f"query-plan-{index}")),
            kind=str(data.get("kind", "query")),
            query_ref=str(data.get("query_ref", "")),
            timeout_ms=int(data.get("timeout_ms", 1_000) or 1_000),
            rate_limit_per_minute=int(data.get("rate_limit_per_minute", 10) or 10),
        )

    @property
    def safe_budget(self) -> bool:
        return 0 < self.timeout_ms <= _MAX_TIMEOUT_MS and 0 < self.rate_limit_per_minute <= _MAX_RATE_LIMIT_PER_MINUTE

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "query_ref": self.query_ref,
            "timeout_ms": self.timeout_ms,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "safe_budget": self.safe_budget,
        }


@dataclass(frozen=True)
class StagingConnectorManifest:
    id: str
    provider: str
    environment: str
    endpoint_ref: str
    credential_ref: str
    declared_scopes: tuple[str, ...]
    operations: tuple[str, ...]
    query_plans: tuple[StagingQueryPlan, ...]
    sample_response: Mapping[str, Any]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StagingConnectorManifest:
        query_plans = tuple(
            StagingQueryPlan.from_dict(item, index=index)
            for index, item in enumerate(_sequence(data.get("query_plans", ())), start=1)
            if isinstance(item, Mapping)
        )
        return cls(
            id=str(data.get("id", "staging-connector")),
            provider=str(data.get("provider", "unknown")).lower(),
            environment=str(data.get("environment", "unknown")).lower(),
            endpoint_ref=str(data.get("endpoint_ref", "")),
            credential_ref=str(data.get("credential_ref", "")),
            declared_scopes=tuple(str(item) for item in _sequence(data.get("declared_scopes", ()))),
            operations=tuple(str(item) for item in _sequence(data.get("operations", ()))),
            query_plans=query_plans,
            sample_response=_mapping(data.get("sample_response")),
        )


@dataclass(frozen=True)
class StagingConnectorContractResult:
    manifest: StagingConnectorManifest
    status: str
    reasons: tuple[str, ...]
    required_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    safe_scopes: bool
    safe_operations: bool
    safe_endpoint_ref: bool
    safe_credential_ref: bool
    staging_environment: bool
    safe_query_budget: bool

    @property
    def schema_compatible(self) -> bool:
        return not self.missing_fields

    @property
    def read_only_safe(self) -> bool:
        return self.safe_scopes and self.safe_operations and self.safe_endpoint_ref and self.safe_credential_ref

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "connector_id": self.manifest.id,
            "provider": self.manifest.provider,
            "environment": self.manifest.environment,
            "endpoint_ref": self.manifest.endpoint_ref,
            "credential_ref": _safe_credential_display(self.manifest.credential_ref),
            "declared_scopes": list(self.manifest.declared_scopes),
            "operations": list(self.manifest.operations),
            "status": self.status,
            "reasons": list(self.reasons),
            "read_only_safe": self.read_only_safe,
            "staging_environment": self.staging_environment,
            "schema": {
                "required_fields": list(self.required_fields),
                "observed_fields": sorted(str(key) for key in self.manifest.sample_response.keys()),
                "missing_fields": list(self.missing_fields),
                "compatible": self.schema_compatible,
            },
            "query_plans": [plan.to_dict() for plan in self.manifest.query_plans],
            "safe_query_budget": self.safe_query_budget,
            "live_api_called": False,
            "production_mutation_count": 0,
            "action_execution_count": 0,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class StagingReadOnlyConnectorContractReport:
    results: tuple[StagingConnectorContractResult, ...]

    def to_dict(self) -> dict[str, Any]:
        ready = tuple(result for result in self.results if result.status == "ready")
        degraded = tuple(result for result in self.results if result.status == "degraded")
        blocked = tuple(result for result in self.results if result.status == "blocked")
        ready_providers = {result.manifest.provider for result in ready}
        schema_compatible = tuple(result for result in self.results if result.schema_compatible)
        read_only_safe = tuple(result for result in self.results if result.read_only_safe)
        staging = tuple(result for result in self.results if result.staging_environment)
        provider_coverage_rate = _ratio(sum(1 for provider in _REQUIRED_PROVIDERS if provider in ready_providers), len(_REQUIRED_PROVIDERS))
        payload = {
            "summary": {
                "connector_count": len(self.results),
                "ready_count": len(ready),
                "degraded_count": len(degraded),
                "blocked_count": len(blocked),
                "provider_count": len(ready_providers),
                "schema_compatible_count": len(schema_compatible),
                "passed": len(self.results) >= 4 and len(ready) >= 3 and len(blocked) >= 1 and provider_coverage_rate == 1.0,
            },
            "score": {
                "provider_coverage_rate": provider_coverage_rate,
                "read_only_safety_rate": _ratio(len(read_only_safe), len(self.results)),
                "staging_environment_rate": _ratio(len(staging), len(self.results)),
                "schema_compatibility_rate": _ratio(len(schema_compatible), len(self.results)),
                "live_api_call_count": 0,
                "production_mutation_count": 0,
                "action_execution_count": 0,
            },
            "boundary": dict(_BOUNDARY),
            "operator_handoff": _operator_handoff(ready, blocked),
            "connectors": [result.to_dict() for result in self.results],
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


class StagingReadOnlyConnectorContractRunner:
    def run_path(self, path: str | Path) -> StagingReadOnlyConnectorContractReport:
        return self.run(load_staging_connector_contract_manifests(path))

    def run(self, manifests: Sequence[StagingConnectorManifest]) -> StagingReadOnlyConnectorContractReport:
        return StagingReadOnlyConnectorContractReport(results=tuple(_evaluate_manifest(manifest) for manifest in manifests))


def load_staging_connector_contract_manifests(path: str | Path) -> tuple[StagingConnectorManifest, ...]:
    local_path = _ensure_local_path(path)
    data = json.loads(local_path.read_text(encoding="utf-8"))
    raw = data.get("connectors", ()) if isinstance(data, Mapping) else data
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        raise ValueError("staging connector contract manifest must contain connectors")
    return tuple(StagingConnectorManifest.from_dict(item) for item in raw if isinstance(item, Mapping))


def run_staging_read_only_connector_contract_fixture(path: str | Path) -> StagingReadOnlyConnectorContractReport:
    return StagingReadOnlyConnectorContractRunner().run_path(path)


def render_staging_read_only_connector_contract_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("score"))
    handoff = _mapping(payload.get("operator_handoff"))
    lines = [
        "# OpsCat Staging Read-only Connector Contract",
        "",
        "Boundary: staging connector contract only; local manifest and sample responses; no live API calls; no production mutation; no remediation execution.",
        "",
        "## Summary",
        f"- Connectors: {summary.get('connector_count')}",
        f"- Ready connectors: {summary.get('ready_count')}",
        f"- Degraded connectors: {summary.get('degraded_count')}",
        f"- Blocked connectors: {summary.get('blocked_count')}",
        f"- Provider count: {summary.get('provider_count')}",
        "",
        "## Provider coverage",
        f"- provider_coverage_rate: {score.get('provider_coverage_rate')}",
        f"- read_only_safety_rate: {score.get('read_only_safety_rate')}",
        f"- staging_environment_rate: {score.get('staging_environment_rate')}",
        f"- schema_compatibility_rate: {score.get('schema_compatibility_rate')}",
        f"- live_api_call_count: {score.get('live_api_call_count')}",
        "",
        "## Operator handoff",
        f"- Ready connectors: {', '.join(str(item) for item in _sequence(handoff.get('ready_connectors', ())))}",
        f"- Blocked connectors: {', '.join(str(item) for item in _sequence(handoff.get('blocked_connectors', ())))}",
        f"- Next step: {handoff.get('next_step')}",
        "",
        "## Connectors",
    ]
    for item in _sequence(payload.get("connectors", ())):
        if isinstance(item, Mapping):
            reasons = ",".join(str(reason) for reason in _sequence(item.get("reasons", ())))
            lines.append(f"- `{item.get('connector_id')}` provider={item.get('provider')} status={item.get('status')} reasons={reasons}")
    return "\n".join(lines) + "\n"


def write_staging_read_only_connector_contract_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_staging_read_only_connector_contract_markdown(payload), encoding="utf-8")


def _evaluate_manifest(manifest: StagingConnectorManifest) -> StagingConnectorContractResult:
    required_fields = _PROVIDER_REQUIRED_FIELDS.get(manifest.provider, ())
    missing_fields = tuple(field for field in required_fields if field not in manifest.sample_response)
    safe_scopes = not any(_contains_marker(scope, _WRITE_SCOPE_MARKERS) for scope in manifest.declared_scopes)
    safe_operations = not any(_contains_marker(operation, _MUTATION_OPERATION_MARKERS) for operation in manifest.operations)
    safe_endpoint_ref = _safe_endpoint_ref(manifest.endpoint_ref)
    safe_credential_ref = _safe_credential_ref(manifest.credential_ref)
    staging_environment = manifest.environment == "staging"
    safe_query_budget = bool(manifest.query_plans) and all(plan.safe_budget for plan in manifest.query_plans)
    reasons: list[str] = []

    if not required_fields:
        reasons.append("unsupported_provider")
    if not staging_environment:
        if manifest.environment == "production":
            reasons.append("production_environment")
        else:
            reasons.append("non_staging_environment")
    if not safe_scopes:
        reasons.append("write_or_admin_scope")
    if not safe_operations:
        reasons.append("mutation_operation")
    if not safe_endpoint_ref:
        reasons.append("raw_endpoint_url")
    if not safe_credential_ref:
        reasons.append("raw_credential_value")
    if missing_fields:
        reasons.append("schema_missing_required_fields")
    if not manifest.query_plans:
        reasons.append("missing_query_plan")
    elif not safe_query_budget:
        reasons.append("unsafe_query_budget")

    blocking_reasons = {
        "unsupported_provider",
        "production_environment",
        "write_or_admin_scope",
        "mutation_operation",
        "raw_endpoint_url",
        "raw_credential_value",
    }
    if any(reason in blocking_reasons for reason in reasons):
        status = "blocked"
    elif reasons:
        status = "degraded"
    else:
        status = "ready"
        reasons.append("staging_read_only_contract_ready")

    return StagingConnectorContractResult(
        manifest=manifest,
        status=status,
        reasons=tuple(reasons),
        required_fields=required_fields,
        missing_fields=missing_fields,
        safe_scopes=safe_scopes,
        safe_operations=safe_operations,
        safe_endpoint_ref=safe_endpoint_ref,
        safe_credential_ref=safe_credential_ref,
        staging_environment=staging_environment,
        safe_query_budget=safe_query_budget,
    )


def _operator_handoff(ready: Sequence[StagingConnectorContractResult], blocked: Sequence[StagingConnectorContractResult]) -> dict[str, Any]:
    return {
        "ready_connectors": [result.manifest.id for result in ready],
        "blocked_connectors": [result.manifest.id for result in blocked],
        "next_step": "attach staging read-only credentials behind manual approval",
    }


def _safe_endpoint_ref(value: str) -> bool:
    lowered = value.lower()
    return bool(value) and not lowered.startswith(_REMOTE_PREFIXES) and lowered.startswith(_SAFE_ENDPOINT_PREFIXES)


def _safe_credential_ref(value: str) -> bool:
    lowered = value.lower()
    return bool(value) and lowered.startswith(_SAFE_CREDENTIAL_PREFIXES)


def _safe_credential_display(value: str) -> str:
    return value if _safe_credential_ref(value) else REDACTED


def _contains_marker(value: str, markers: Sequence[str]) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in markers)


def _ensure_local_path(path: str | Path) -> Path:
    value = str(path)
    if value.lower().startswith(_REMOTE_PREFIXES):
        raise ValueError("remote staging connector contract manifests are not allowed for normal verification")
    local_path = Path(value)
    if not local_path.exists():
        raise FileNotFoundError(f"staging connector contract manifest does not exist: {local_path}")
    return local_path


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 3) if denominator else 0.0


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()
