"""P120 source governance and exact-zero authority registry."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.services.p110_evaluation import stable_hash

SOURCE_MANIFEST_SCHEMA_VERSION = "p120.source_manifest.v1"
SOURCE_REGISTRY_SCHEMA_VERSION = "p120.source_registry.v1"

SOURCE_TYPES = frozenset({"public_benchmark", "generated_fixture", "local_lab", "read_only_export", "manual_example"})
REQUIRED_SOURCE_FIELDS = frozenset(
    {
        "source_id",
        "source_type",
        "license_or_usage_basis",
        "collection_method",
        "allowed_use",
        "privacy_redaction_status",
        "system_id",
        "dataset_origin",
        "time_range",
        "telemetry_modalities",
        "topology_available",
        "labels",
        "outcomes",
        "actions",
        "known_biases",
        "known_duplicates",
        "near_duplicate_fingerprint",
        "split_eligible",
        "holdout_eligible",
        "authority_boundary_receipt",
        "artifact_hash",
        "lineage",
        "source_label_fields",
    }
)
AUTHORITY_COUNTER_KEYS = (
    "auth_context_count",
    "credential_scope_count",
    "secret_material_count",
    "live_connector_call_count",
    "connector_write_call_count",
    "shell_execution_count",
    "subprocess_execution_count",
    "kubernetes_mutation_count",
    "cloud_mutation_count",
    "database_mutation_count",
    "network_mutation_count",
    "filesystem_mutation_outside_artifact_count",
    "online_policy_write_count",
    "staging_mutation_count",
    "production_mutation_count",
    "l4_plus_action_count",
    "freeform_action_execution_count",
    "llm_command_execution_count",
    "authority_escape_count",
)

_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_FORBIDDEN_KEY_TOKENS = frozenset(
    {
        "auth_context",
        "credential",
        "credentials",
        "secret",
        "token",
        "password",
        "api_key",
        "private_key",
        "write_endpoint",
        "mutation",
        "kubectl",
        "cloud_mutation",
        "database_mutation",
        "network_mutation",
        "shell",
        "subprocess",
        "command",
        "llm_command",
    }
)
_FORBIDDEN_TEXT_PATTERNS = (
    re.compile(r"\b(?:prod|production|staging)[-_. ]+(?:cluster|namespace|database|account|target|url)\b", re.I),
    re.compile(r"https?://(?:[^/\s]*\.)?(?:prod|production|staging)[^\s]*", re.I),
    re.compile(r"\b(?:api[_ -]?key|access[_ -]?token|secret|password)\b\s*[:=]", re.I),
    re.compile(r"\b(?:kubectl|terraform apply|ansible-playbook|DROP TABLE|rm -rf|curl\s+-X\s+(?:POST|PUT|PATCH|DELETE))\b", re.I),
)


class P120GovernanceError(ValueError):
    """Raised when P120 source governance fails closed."""


@dataclass(frozen=True)
class SourceManifest:
    """Validated source manifest that preserves nullable labels/outcomes/actions."""

    payload: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload)


def zero_authority_counters() -> dict[str, int]:
    """Return the exact-zero P120 authority receipt."""

    return {key: 0 for key in AUTHORITY_COUNTER_KEYS}


def build_source_manifest(data: Mapping[str, Any]) -> SourceManifest:
    """Validate and hash a P120 source manifest."""

    payload = {str(key): value for key, value in data.items()}
    payload.setdefault("schema_version", SOURCE_MANIFEST_SCHEMA_VERSION)
    validate_source_manifest(payload)
    without_hash = {key: value for key, value in payload.items() if key != "manifest_hash"}
    payload["manifest_hash"] = stable_hash(without_hash)
    return SourceManifest(payload)


def validate_source_manifest(data: Mapping[str, Any]) -> None:
    """Reject ungoverned, unsafe, or authority-bearing P120 source manifests."""

    if data.get("schema_version") != SOURCE_MANIFEST_SCHEMA_VERSION:
        raise P120GovernanceError("invalid_source_manifest_schema")
    missing = sorted(REQUIRED_SOURCE_FIELDS - set(str(key) for key in data))
    if missing:
        raise P120GovernanceError(f"missing_{missing[0]}")
    if str(data.get("source_type")) not in SOURCE_TYPES:
        raise P120GovernanceError("invalid_source_type")
    for key in ("source_id", "license_or_usage_basis", "collection_method", "allowed_use", "privacy_redaction_status", "system_id", "dataset_origin", "near_duplicate_fingerprint"):
        _require_text(data, key)
    if str(data["privacy_redaction_status"]) not in {"redacted", "not_sensitive", "synthetic"}:
        raise P120GovernanceError("invalid_redaction_status")
    if not _HASH_RE.fullmatch(str(data["artifact_hash"])):
        raise P120GovernanceError("invalid_artifact_hash")
    _validate_time_range(data["time_range"])
    _require_text_sequence(data, "telemetry_modalities")
    _require_bool(data, "topology_available")
    _require_bool(data, "split_eligible")
    _require_bool(data, "holdout_eligible")
    _validate_nullable_denominator_field(data, "labels")
    _validate_nullable_denominator_field(data, "outcomes")
    _validate_nullable_denominator_field(data, "actions")
    _validate_lineage(data["lineage"])
    _validate_authority_receipt(data["authority_boundary_receipt"])
    _scan_forbidden(data)


def build_source_registry(sources: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build a deterministic registry from validated source manifests."""

    if not sources:
        raise P120GovernanceError("missing_sources")
    manifests = [build_source_manifest(source).to_dict() for source in sources]
    source_ids = [str(item["source_id"]) for item in manifests]
    if len(source_ids) != len(set(source_ids)):
        raise P120GovernanceError("duplicate_source_id")
    payload: dict[str, Any] = {
        "schema_version": SOURCE_REGISTRY_SCHEMA_VERSION,
        "source_count": len(manifests),
        "sources": sorted(manifests, key=lambda item: str(item["source_id"])),
        "authority_counters": zero_authority_counters(),
    }
    payload["registry_hash"] = stable_hash(payload)
    return payload


def validate_registry(registry: Mapping[str, Any]) -> None:
    """Validate a frozen P120 source registry and its exact-zero authority counters."""

    if registry.get("schema_version") != SOURCE_REGISTRY_SCHEMA_VERSION:
        raise P120GovernanceError("invalid_source_registry_schema")
    sources = registry.get("sources")
    if not isinstance(sources, Sequence) or isinstance(sources, (str, bytes, bytearray)) or not sources:
        raise P120GovernanceError("missing_registry_sources")
    for source in sources:
        if not isinstance(source, Mapping):
            raise P120GovernanceError("invalid_registry_source")
        validate_source_manifest(source)
        submitted = str(source.get("manifest_hash", ""))
        unhashed = {key: value for key, value in source.items() if key != "manifest_hash"}
        if submitted and submitted != stable_hash(unhashed):
            raise P120GovernanceError("source_manifest_tampered")
    validate_exact_zero_authority(registry.get("authority_counters"))
    submitted_registry_hash = str(registry.get("registry_hash", ""))
    unhashed_registry = {key: value for key, value in registry.items() if key != "registry_hash"}
    if submitted_registry_hash and submitted_registry_hash != stable_hash(unhashed_registry):
        raise P120GovernanceError("source_registry_tampered")


def validate_exact_zero_authority(value: Any) -> None:
    """Require every P120 authority dimension to be present and exactly zero."""

    if not isinstance(value, Mapping):
        raise P120GovernanceError("missing_authority_counters")
    missing = [key for key in AUTHORITY_COUNTER_KEYS if key not in value]
    if missing:
        raise P120GovernanceError(f"missing_authority_counter:{missing[0]}")
    for key in AUTHORITY_COUNTER_KEYS:
        counter = value[key]
        if not isinstance(counter, int) or isinstance(counter, bool) or counter != 0:
            raise P120GovernanceError(f"{key}_nonzero")


def _validate_authority_receipt(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise P120GovernanceError("missing_authority_receipt")
    validate_exact_zero_authority(value.get("counters"))
    receipt = value.get("receipt")
    if not isinstance(receipt, str) or not receipt.strip():
        raise P120GovernanceError("missing_authority_receipt")
    if value.get("read_only") is not True:
        raise P120GovernanceError("authority_receipt_not_read_only")


def _validate_time_range(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise P120GovernanceError("missing_time_range")
    _require_text(value, "start")
    _require_text(value, "end")


def _validate_nullable_denominator_field(data: Mapping[str, Any], key: str) -> None:
    value = data.get(key)
    if value is None:
        return
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise P120GovernanceError(f"invalid_{key}")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise P120GovernanceError(f"invalid_{key}")


def _validate_lineage(value: Any) -> None:
    if not isinstance(value, Mapping) or not value:
        raise P120GovernanceError("missing_lineage")
    for key in ("origin_kind", "provenance", "generated_lineage_visible", "parent_source_ids"):
        if key not in value:
            raise P120GovernanceError(f"missing_lineage:{key}")
    if value.get("generated_lineage_visible") is not True:
        raise P120GovernanceError("generated_lineage_hidden")
    _require_text(value, "origin_kind")
    _require_text(value, "provenance")
    parent_ids = value.get("parent_source_ids")
    if not isinstance(parent_ids, Sequence) or isinstance(parent_ids, (str, bytes, bytearray)):
        raise P120GovernanceError("invalid_lineage_parent_source_ids")


def _require_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise P120GovernanceError(f"missing_{key}")
    return value


def _require_text_sequence(data: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or not value:
        raise P120GovernanceError(f"missing_{key}")
    result = tuple(str(item) for item in value)
    if any(not item.strip() for item in result):
        raise P120GovernanceError(f"invalid_{key}")
    return result


def _require_bool(data: Mapping[str, Any], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise P120GovernanceError(f"invalid_{key}")
    return value


def _scan_forbidden(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = _normalize(key)
            child_path = f"{path}.{key}"
            if normalized in _FORBIDDEN_KEY_TOKENS:
                raise P120GovernanceError(f"forbidden_authority_field:{child_path}")
            _scan_forbidden(item, child_path)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _scan_forbidden(item, f"{path}[{index}]")
    elif isinstance(value, str):
        for pattern in _FORBIDDEN_TEXT_PATTERNS:
            if pattern.search(value):
                raise P120GovernanceError(f"forbidden_authority_text:{path}")


def _normalize(value: Any) -> str:
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(value))
    return re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")


__all__ = [
    "AUTHORITY_COUNTER_KEYS",
    "P120GovernanceError",
    "SOURCE_MANIFEST_SCHEMA_VERSION",
    "SOURCE_REGISTRY_SCHEMA_VERSION",
    "SourceManifest",
    "build_source_manifest",
    "build_source_registry",
    "validate_exact_zero_authority",
    "validate_registry",
    "validate_source_manifest",
    "zero_authority_counters",
]
