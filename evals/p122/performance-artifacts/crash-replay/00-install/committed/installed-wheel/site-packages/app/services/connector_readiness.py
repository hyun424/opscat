"""P27 connector readiness and permission contract.

This module evaluates local/mock connector manifests before any live-like polling.
It never calls external services and never executes remediation actions.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.redaction import redact_value

_ALLOWED_CAPABILITIES = frozenset({"read", "query", "list", "health", "metadata"})
_MUTATION_MARKERS = (
    "write",
    "delete",
    "restart",
    "shell",
    "shell_execute",
    "kubectl",
    "exec",
    "deploy",
    "rollback",
    "mutate",
    "update",
    "create",
    "patch",
    "purge",
)
_HEALTH_RETRY_SECONDS = {
    "ok": 0,
    "missing_credential": 60,
    "rate_limit": 120,
    "timeout": 120,
    "schema_error": 180,
    "auth_failure": 300,
    "permission_denied": 300,
    "unavailable": 300,
}
_BOUNDARY: dict[str, bool] = {
    "local_mock_only": True,
    "read_only_connector_readiness": True,
    "live_api_calls_enabled": False,
    "live_writes_enabled": False,
    "remediation_execution_enabled": False,
    "production_mutation_enabled": False,
    "default_external_model_calls": False,
}


@dataclass(frozen=True)
class CredentialReference:
    name: str
    required: bool = True
    present: bool = True

    @classmethod
    def from_value(cls, value: Any) -> CredentialReference | None:
        if value is None:
            return None
        if isinstance(value, str):
            return cls(name=value)
        if isinstance(value, Mapping):
            return cls(name=str(value.get("name", "")), required=bool(value.get("required", True)), present=bool(value.get("present", True)))
        return None

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "required": self.required, "present": self.present}


@dataclass(frozen=True)
class ConnectorManifest:
    source: str
    capabilities: tuple[str, ...]
    required_scopes: tuple[str, ...]
    read_only: bool
    credential_ref: CredentialReference | None
    health: str
    evidence_id: str
    poll_enabled: bool = False
    raw_metadata: Mapping[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, index: int) -> ConnectorManifest:
        return cls(
            source=str(data.get("source", f"source-{index}")),
            capabilities=tuple(str(item) for item in _sequence(data.get("capabilities", ()))),
            required_scopes=tuple(str(item) for item in _sequence(data.get("required_scopes", ()))),
            read_only=bool(data.get("read_only", False)),
            credential_ref=CredentialReference.from_value(data.get("credential_ref")),
            health=str(data.get("health", "ok")),
            evidence_id=str(data.get("evidence_id", f"connector-manifest-{index}")),
            poll_enabled=bool(data.get("poll_enabled", False)),
            raw_metadata=_as_mapping(data.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "source": self.source,
            "capabilities": list(self.capabilities),
            "required_scopes": list(self.required_scopes),
            "read_only": self.read_only,
            "credential_ref": self.credential_ref.to_dict() if self.credential_ref else None,
            "health": self.health,
            "evidence_id": self.evidence_id,
            "poll_enabled": self.poll_enabled,
            "metadata": dict(self.raw_metadata or {}),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class ConnectorReadinessSource:
    source: str
    state: str
    reasons: tuple[str, ...]
    allowed_capabilities: tuple[str, ...]
    denied_capabilities: tuple[str, ...]
    required_scopes: tuple[str, ...]
    credential_ref: CredentialReference | None
    evidence_ids: tuple[str, ...]
    next_safe_retry_seconds: int
    poll_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "source": self.source,
            "state": self.state,
            "reasons": list(self.reasons),
            "allowed_capabilities": list(self.allowed_capabilities),
            "denied_capabilities": list(self.denied_capabilities),
            "required_scopes": list(self.required_scopes),
            "credential_ref": self.credential_ref.to_dict() if self.credential_ref else None,
            "evidence_ids": list(self.evidence_ids),
            "next_safe_retry_seconds": self.next_safe_retry_seconds,
            "poll_enabled": self.poll_enabled,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class ConnectorReadinessReport:
    sources: tuple[ConnectorReadinessSource, ...]

    def to_dict(self) -> dict[str, Any]:
        source_payloads = [source.to_dict() for source in self.sources]
        mutation_count = sum(len(source.denied_capabilities) for source in self.sources)
        tight_loop_risk_count = sum(1 for source in self.sources if source.state in {"degraded", "unavailable"} and source.next_safe_retry_seconds <= 0)
        payload = {
            "summary": {
                "source_count": len(self.sources),
                "ready_count": sum(1 for source in self.sources if source.state == "ready"),
                "degraded_count": sum(1 for source in self.sources if source.state == "degraded"),
                "blocked_count": sum(1 for source in self.sources if source.state == "blocked"),
                "unavailable_count": sum(1 for source in self.sources if source.state == "unavailable"),
            },
            "score": {
                "mutation_capability_count": mutation_count,
                "tight_loop_risk_count": tight_loop_risk_count,
                "poll_enabled_count": sum(1 for source in self.sources if source.poll_enabled),
            },
            "boundary": dict(_BOUNDARY),
            "sources": source_payloads,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


class ConnectorReadinessEvaluator:
    def evaluate_path(self, path: str | Path) -> ConnectorReadinessReport:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, Mapping):
            raise ValueError("connector readiness fixture must be an object")
        manifests = [ConnectorManifest.from_dict(item, index=index) for index, item in enumerate(_sequence(data.get("sources", ())), start=1) if isinstance(item, Mapping)]
        return self.evaluate(manifests)

    def evaluate(self, manifests: Sequence[ConnectorManifest]) -> ConnectorReadinessReport:
        return ConnectorReadinessReport(sources=tuple(self._evaluate_manifest(manifest) for manifest in manifests))

    def _evaluate_manifest(self, manifest: ConnectorManifest) -> ConnectorReadinessSource:
        denied = tuple(capability for capability in manifest.capabilities if _is_mutation_capability(capability) or capability not in _ALLOWED_CAPABILITIES)
        allowed = tuple(capability for capability in manifest.capabilities if capability in _ALLOWED_CAPABILITIES and capability not in denied)
        reasons: list[str] = []
        retry_seconds = _HEALTH_RETRY_SECONDS.get(manifest.health, 300)
        state = "ready"

        if denied or not manifest.read_only:
            state = "blocked"
            if denied:
                reasons.append("mutation_capability_declared")
            if not manifest.read_only:
                reasons.append("read_only_false")
            retry_seconds = 0
        elif manifest.credential_ref is not None and manifest.credential_ref.required and not manifest.credential_ref.present:
            state = "degraded"
            reasons.append("missing_credential")
            retry_seconds = max(retry_seconds, _HEALTH_RETRY_SECONDS["missing_credential"])
        elif manifest.health in {"rate_limit", "timeout", "schema_error", "permission_denied"}:
            state = "degraded"
            reasons.append(manifest.health)
        elif manifest.health in {"auth_failure", "unavailable"}:
            state = "unavailable"
            reasons.append(manifest.health)
        elif manifest.health != "ok":
            state = "degraded"
            reasons.append(manifest.health)

        if manifest.poll_enabled:
            reasons.append("polling_explicitly_enabled")
        if not reasons:
            reasons.append("read_only_ready")

        return ConnectorReadinessSource(
            source=manifest.source,
            state=state,
            reasons=tuple(reasons),
            allowed_capabilities=allowed,
            denied_capabilities=denied,
            required_scopes=manifest.required_scopes,
            credential_ref=manifest.credential_ref,
            evidence_ids=(manifest.evidence_id,),
            next_safe_retry_seconds=retry_seconds,
            poll_enabled=manifest.poll_enabled,
        )


def evaluate_connector_readiness_fixture(path: str | Path) -> ConnectorReadinessReport:
    return ConnectorReadinessEvaluator().evaluate_path(path)


def render_connector_readiness_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), Mapping) else {}
    score = payload.get("score", {}) if isinstance(payload.get("score"), Mapping) else {}
    lines = [
        "# OpsCat Connector Readiness Report",
        "",
        "Boundary: read-only connector readiness; no-auth/local-mock by default; no live writes; no remediation execution; no production mutation; does not claim unattended production operation.",
        "",
        "## Summary",
        f"- Sources: {summary.get('source_count')}",
        f"- Ready: {summary.get('ready_count')}",
        f"- Degraded: {summary.get('degraded_count')}",
        f"- Blocked: {summary.get('blocked_count')}",
        f"- Unavailable: {summary.get('unavailable_count')}",
        "",
        "## Score",
        f"- mutation_capability_count: {score.get('mutation_capability_count')}",
        f"- tight_loop_risk_count: {score.get('tight_loop_risk_count')}",
        f"- poll_enabled_count: {score.get('poll_enabled_count')}",
        "",
        "## Sources",
    ]
    sources = payload.get("sources", [])
    if isinstance(sources, Sequence) and not isinstance(sources, (str, bytes, bytearray)):
        for source in sources:
            if isinstance(source, Mapping):
                reasons = ",".join(str(item) for item in _sequence(source.get("reasons", ())))
                lines.append(f"- `{source.get('source')}` state={source.get('state')} retry={source.get('next_safe_retry_seconds')} reasons={reasons}")
    return "\n".join(lines) + "\n"


def write_connector_readiness_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_connector_readiness_markdown(payload), encoding="utf-8")


def _is_mutation_capability(capability: str) -> bool:
    lowered = capability.lower()
    return any(marker in lowered for marker in _MUTATION_MARKERS)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()
