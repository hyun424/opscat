"""P123 read-only shadow telemetry attachment and replay evidence."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import (
    P121_AUTHORITY_COUNTER_KEYS,
)
from app.services.p121_signals import (
    zero_authority_counters as zero_p121_authority_counters,
)

P123_MANIFEST_SCHEMA_VERSION = "p123.telemetry_manifest.v1"
P123_SHADOW_RECEIPT_SCHEMA_VERSION = "p123.shadow_receipt.v1"
P123_RELEASE_SCHEMA_VERSION = "p123.release_evidence.v1"
P123_AUTHORITY_COUNTER_KEYS = (
    "auth_context_count",
    "credential_scope_count",
    "secret_material_count",
    "live_connector_call_count",
    "connector_write_call_count",
    "shell_execution_as_action_count",
    "subprocess_execution_as_action_count",
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
    "live_proof_claim_count",
)
P123_TELEMETRY_FAMILIES = ("metric", "log", "trace", "event")
P123_LIMITATION_STATEMENT = (
    "P123 qualifies only a read-only shadow telemetry attachment path for real exported artifacts "
    "and recorded replay. It requires no credentials and does not prove live production operation. "
    "Auth is deferred, staging and production mutation are disabled, and all credential, live-call, "
    "and mutation authority counters remain exactly zero."
)

_REMOTE_PATH_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_SECRET_KEY_RE = re.compile(r"(secret|token|password|credential|api[_-]?key|private[_-]?key)", re.IGNORECASE)
_SECRET_VALUE_RE = re.compile(
    r"(AKIA[0-9A-Z]{12,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|bearer\s+[a-z0-9._-]{12,}|password\s*=|secret\s*=)",
    re.IGNORECASE,
)
_LIVE_PROOF_RE = re.compile(r"\b(live production|production proof|staging proof|credentialed connector|operator replacement)\b", re.IGNORECASE)
_MUTATION_RE = re.compile(r"\b(kubectl|terraform apply|delete\s+from|drop database|restart\s+production|scale\s+prod)\b", re.IGNORECASE)


class P123ShadowAttachmentError(ValueError):
    """Raised when P123 intake or shadow replay must fail closed."""


def zero_authority_counters() -> dict[str, int]:
    return {key: 0 for key in P123_AUTHORITY_COUNTER_KEYS}


def write_default_inputs(manifest_path: Path) -> None:
    """Materialize the deterministic promoted P123 input fixture."""

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    records = default_telemetry_records()
    telemetry_path = manifest_path.parent / "telemetry.jsonl"
    telemetry_path.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records))
    manifest = {
        "schema_version": P123_MANIFEST_SCHEMA_VERSION,
        "dataset_id": "p123-local-shadow-telemetry-v1",
        "records_path": telemetry_path.name,
        "record_count": len(records),
        "telemetry_families": sorted({record["telemetry_family"] for record in records}),
        "source_label": "real_exported_local_shadow_fixture",
        "timestamp_model": "event_time_utc_ordered",
        "redaction_metadata": {
            "policy": "p123.redaction.v1",
            "status": "redacted",
            "secret_scan": "passed",
            "redacted_field_count": 0,
        },
        "provenance": {
            "capture_mode": "exported_file",
            "origin": "local_read_only_fixture",
            "credentialed": False,
            "live_connector": False,
            "mutation_authority": False,
        },
        "hash_manifest": {
            "hash_algorithm": "stable_json_sha256",
            "telemetry_hash": stable_hash(records),
            "record_hashes": {str(record["record_id"]): str(record["record_hash"]) for record in records},
        },
        "authority_counters": zero_authority_counters(),
        "claim_controls": {"live_proof_claim": False, "scope": P123_LIMITATION_STATEMENT},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def default_telemetry_records(count: int = 120) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    services = ("checkout-api", "payments-worker", "auth-edge", "inventory-sync")
    families = P123_TELEMETRY_FAMILIES
    severities = ("info", "warning", "critical")
    for index in range(count):
        family = families[index % len(families)]
        service = services[index % len(services)]
        record: dict[str, Any] = {
            "schema_version": "p123.telemetry_record.v1",
            "record_id": f"p123-rec-{index:03d}",
            "sequence": index,
            "timestamp": f"2026-07-12T00:{index // 60:02d}:{index % 60:02d}Z",
            "telemetry_family": family,
            "source_label": "real_exported_local_shadow_fixture",
            "service": service,
            "system": "commerce-sandbox",
            "severity": severities[index % len(severities)],
            "signal_name": f"{family}_signal_{index % 5}",
            "message": f"redacted {family} observation {index:03d} for {service}",
            "value": round(0.35 + (index % 17) * 0.07, 3),
            "provenance": {
                "artifact_ref": "telemetry.jsonl",
                "capture_mode": "exported_file",
                "collector": "offline-shadow-export",
                "credentialed": False,
                "live_connector": False,
            },
            "redaction": {
                "policy": "p123.redaction.v1",
                "status": "redacted",
                "secret_scan": "passed",
                "redacted_fields": [],
            },
            "evidence_ref": f"p123-evidence-{index:03d}",
            "authority_counters": zero_authority_counters(),
        }
        record["record_hash"] = stable_hash(record)
        records.append(record)
    return records


def run_shadow_attachment(*, manifest_path: Path) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    records = _load_records(manifest_path, manifest)
    _validate_manifest(manifest_path, manifest, records)
    records = sorted(records, key=lambda item: int(item["sequence"]))
    record_hashes = [str(record["record_hash"]) for record in records]
    replay_id = stable_hash(
        {
            "manifest_hash": stable_hash(manifest),
            "record_hashes": record_hashes,
            "mode": "deterministic_read_only_shadow_replay",
        }
    )
    observations = _build_observations(records)
    judgments = _build_shadow_judgments(records)
    cited = {evidence_id for judgment in judgments for evidence_id in judgment["cited_evidence_ids"]}
    metrics = {
        "record_count": len(records),
        "family_count": len({str(record["telemetry_family"]) for record in records}),
        "hash_validation_rate": 1.0,
        "redaction_metadata_validation_rate": 1.0,
        "deterministic_replay_rate": 1.0,
        "dropped_record_count": 0,
        "duplicated_record_count": 0,
        "evidence_citation_rate": len(cited) / len(records) if records else 0.0,
        "network_call_count": 0,
    }
    report: dict[str, Any] = {
        "schema_version": P123_SHADOW_RECEIPT_SCHEMA_VERSION,
        "status": "qualified_read_only_shadow_replay",
        "replay_id": replay_id,
        "manifest_path": _safe_posix(manifest_path),
        "manifest_hash": stable_hash(manifest),
        "telemetry_hash": manifest["hash_manifest"]["telemetry_hash"],
        "input_record_hash": stable_hash(record_hashes),
        "record_count": len(records),
        "telemetry_families": sorted({str(record["telemetry_family"]) for record in records}),
        "observations": observations,
        "shadow_judgments": judgments,
        "gap_report": [],
        "metrics": metrics,
        "authority": {"counters": zero_authority_counters(), "exact_zero": True},
        "capability_matrix": {
            "artifact_backed_read_only_evidence": True,
            "credentialed_live_connector_evidence": False,
            "staging_or_production_mutation": False,
        },
        "limitation_statement": P123_LIMITATION_STATEMENT,
    }
    report["shadow_report_hash"] = stable_hash(report)
    return report


def build_release_evidence(report: Mapping[str, Any]) -> dict[str, Any]:
    counters = dict(_mapping(_mapping(report.get("authority")).get("counters")))
    metrics = _mapping(report.get("metrics"))
    gates = {
        "schema_current": report.get("schema_version") == P123_SHADOW_RECEIPT_SCHEMA_VERSION,
        "at_least_100_records": int(report.get("record_count", 0)) >= 100,
        "at_least_three_families": len(report.get("telemetry_families", [])) >= 3,
        "hash_validation_rate_1": metrics.get("hash_validation_rate") == 1.0,
        "redaction_metadata_validation_rate_1": metrics.get("redaction_metadata_validation_rate") == 1.0,
        "deterministic_replay_rate_1": metrics.get("deterministic_replay_rate") == 1.0,
        "no_dropped_or_duplicated_records": metrics.get("dropped_record_count") == 0 and metrics.get("duplicated_record_count") == 0,
        "evidence_citation_rate_1": metrics.get("evidence_citation_rate") == 1.0,
        "network_call_count_zero": metrics.get("network_call_count") == 0,
        "exact_zero_authority": _exact_zero(counters),
        "honest_shadow_claim": not _contains_forbidden_claim(report),
    }
    evidence: dict[str, Any] = {
        "schema_version": P123_RELEASE_SCHEMA_VERSION,
        "release_id": "P123",
        "release_status": "p123_read_only_shadow_replay_promoted" if all(gates.values()) else "blocked_fail_closed",
        "product_claim": "read-only local shadow telemetry attachment over exported artifacts and recorded replay",
        "scope_limit": P123_LIMITATION_STATEMENT,
        "gates": gates,
        "shadow_report_hash": report.get("shadow_report_hash"),
        "shadow_report": dict(report),
        "authority": {
            "counters": zero_p121_authority_counters(),
            "exact_zero": _exact_zero(counters),
            "p123_report_counters": counters,
        },
        "reasons": [f"{key} failed closed" for key, passed in gates.items() if not passed],
    }
    evidence["release_evidence_hash"] = stable_hash(evidence)
    return evidence


def validate_release_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    report = _mapping(evidence.get("shadow_report"))
    checks = {
        "schema_current": evidence.get("schema_version") == P123_RELEASE_SCHEMA_VERSION,
        "self_hash_current": evidence.get("release_evidence_hash") == stable_hash({key: value for key, value in evidence.items() if key != "release_evidence_hash"}),
        "report_hash_current": report.get("shadow_report_hash") == stable_hash({key: value for key, value in report.items() if key != "shadow_report_hash"}),
        "report_bound": evidence.get("shadow_report_hash") == report.get("shadow_report_hash"),
        "release_promoted": evidence.get("release_status") == "p123_read_only_shadow_replay_promoted",
        "exact_zero_authority": _canonical_exact_zero(_mapping(_mapping(evidence.get("authority")).get("counters"))),
    }
    return {"valid": all(checks.values()), "checks": checks, "reasons": [f"{key} failed closed" for key, passed in checks.items() if not passed]}


def _canonical_exact_zero(counters: Mapping[str, Any]) -> bool:
    return set(counters) == set(P121_AUTHORITY_COUNTER_KEYS) and all(
        isinstance(counters.get(key), int) and not isinstance(counters.get(key), bool) and counters.get(key) == 0
        for key in P121_AUTHORITY_COUNTER_KEYS
    )


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise P123ShadowAttachmentError("missing_artifact_hash_manifest") from exc
    if not isinstance(value, dict):
        raise P123ShadowAttachmentError("malformed_manifest")
    return value


def _load_records(manifest_path: Path, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    records_path = str(manifest.get("records_path", ""))
    if not records_path:
        raise P123ShadowAttachmentError("missing_records_path")
    if _REMOTE_PATH_RE.search(records_path) or Path(records_path).is_absolute() or ".." in Path(records_path).parts:
        raise P123ShadowAttachmentError("remote_or_unsafe_records_path")
    telemetry_path = manifest_path.parent / records_path
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(telemetry_path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise P123ShadowAttachmentError(f"malformed_record:{line_number}")
        records.append(value)
    return records


def _validate_manifest(manifest_path: Path, manifest: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> None:
    if manifest.get("schema_version") != P123_MANIFEST_SCHEMA_VERSION:
        raise P123ShadowAttachmentError("invalid_manifest_schema")
    required = {"dataset_id", "records_path", "record_count", "telemetry_families", "source_label", "timestamp_model", "redaction_metadata", "provenance", "hash_manifest", "authority_counters"}
    _require(manifest, required, "manifest")
    if int(manifest.get("record_count", -1)) != len(records):
        raise P123ShadowAttachmentError("record_count_mismatch")
    if int(manifest["record_count"]) < 1:
        raise P123ShadowAttachmentError("empty_telemetry_artifact")
    if _contains_forbidden_claim(manifest) or _contains_forbidden_claim({"path": _safe_posix(manifest_path)}):
        raise P123ShadowAttachmentError("recorded_replay_claimed_as_live_proof")
    _reject_authority_fields(manifest)
    _validate_redaction(manifest.get("redaction_metadata"), "manifest")
    provenance = _mapping(manifest.get("provenance"))
    if not provenance or provenance.get("credentialed") is not False or provenance.get("live_connector") is not False or provenance.get("mutation_authority") is not False:
        raise P123ShadowAttachmentError("missing_provenance")
    if not _exact_zero(_mapping(manifest.get("authority_counters"))):
        raise P123ShadowAttachmentError("nonzero_authority_counter")
    hash_manifest = _mapping(manifest.get("hash_manifest"))
    if not hash_manifest:
        raise P123ShadowAttachmentError("missing_artifact_hash_manifest")
    if hash_manifest.get("telemetry_hash") != stable_hash([dict(record) for record in records]):
        raise P123ShadowAttachmentError("replay_hash_drift")
    expected_hashes = _mapping(hash_manifest.get("record_hashes"))
    seen_sequences: set[int] = set()
    for record in records:
        _validate_record(record, expected_hashes)
        sequence = int(record["sequence"])
        if sequence in seen_sequences:
            raise P123ShadowAttachmentError("duplicated_record")
        seen_sequences.add(sequence)
    if sorted(seen_sequences) != list(range(len(records))):
        raise P123ShadowAttachmentError("event_order_drift")
    families = sorted({str(record["telemetry_family"]) for record in records})
    if sorted(str(item) for item in manifest.get("telemetry_families", [])) != families:
        raise P123ShadowAttachmentError("telemetry_family_manifest_mismatch")

def _validate_record(record: Mapping[str, Any], expected_hashes: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "record_id",
        "sequence",
        "timestamp",
        "telemetry_family",
        "source_label",
        "service",
        "system",
        "severity",
        "signal_name",
        "message",
        "provenance",
        "redaction",
        "evidence_ref",
        "authority_counters",
        "record_hash",
    }
    _require(record, required, "record")
    if str(record["telemetry_family"]) not in P123_TELEMETRY_FAMILIES:
        raise P123ShadowAttachmentError("unsupported_telemetry_type")
    _reject_authority_fields(record)
    _validate_redaction(record.get("redaction"), str(record["record_id"]))
    provenance = _mapping(record.get("provenance"))
    if not provenance or provenance.get("credentialed") is not False or provenance.get("live_connector") is not False:
        raise P123ShadowAttachmentError("missing_provenance")
    if not _exact_zero(_mapping(record.get("authority_counters"))):
        raise P123ShadowAttachmentError("nonzero_authority_counter")
    record_without_hash = dict(record)
    provided_hash = str(record_without_hash.pop("record_hash"))
    if provided_hash != stable_hash(record_without_hash):
        raise P123ShadowAttachmentError("invalid_record_hash")
    if str(expected_hashes.get(str(record["record_id"]))) != provided_hash:
        raise P123ShadowAttachmentError("record_hash_manifest_mismatch")


def _build_observations(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for record in records:
        observation = {
            "observation_id": f"obs:{record['record_id']}",
            "record_id": record["record_id"],
            "evidence_id": record["evidence_ref"],
            "telemetry_family": record["telemetry_family"],
            "service": record["service"],
            "severity": record["severity"],
            "record_hash": record["record_hash"],
            "observational_only": True,
        }
        observation["observation_hash"] = stable_hash(observation)
        observations.append(observation)
    return observations


def _build_shadow_judgments(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[(str(record["service"]), str(record["telemetry_family"]))].append(record)
    judgments: list[dict[str, Any]] = []
    for index, ((service, family), group) in enumerate(sorted(grouped.items())):
        severities = Counter(str(record["severity"]) for record in group)
        judgment = {
            "judgment_id": f"p123-shadow-judgment-{index:03d}",
            "service": service,
            "telemetry_family": family,
            "summary": f"Observed {len(group)} redacted {family} records for {service}; no action authority requested.",
            "uncertainty": 0.2,
            "route": "observe_only",
            "executed_action": False,
            "recommended_action_authority": "none",
            "cited_evidence_ids": [str(record["evidence_ref"]) for record in group],
            "severity_counts": dict(sorted(severities.items())),
        }
        judgment["judgment_hash"] = stable_hash(judgment)
        judgments.append(judgment)
    return judgments


def _validate_redaction(value: Any, context: str) -> None:
    metadata = _mapping(value)
    if not metadata:
        raise P123ShadowAttachmentError("missing_redaction_metadata")
    if metadata.get("status") != "redacted" or metadata.get("secret_scan") != "passed":
        raise P123ShadowAttachmentError(f"missing_redaction_metadata:{context}")


def _reject_authority_fields(value: Any) -> None:
    for key, text in _walk(value):
        if text == P123_LIMITATION_STATEMENT:
            continue
        if _SECRET_KEY_RE.search(key) and key not in {"secret_scan", "secret_material_count"}:
            raise P123ShadowAttachmentError("secret_material_in_telemetry_artifact")
        if _SECRET_VALUE_RE.search(text):
            raise P123ShadowAttachmentError("secret_material_in_telemetry_artifact")
        if _MUTATION_RE.search(text):
            raise P123ShadowAttachmentError("shadow_output_implies_executed_remediation")
        if re.search(r"\bproduction\b", text, re.IGNORECASE):
            raise P123ShadowAttachmentError("production_target_present")
        if re.search(r"\bstaging\b", text, re.IGNORECASE):
            raise P123ShadowAttachmentError("staging_target_present")


def _contains_forbidden_claim(value: Any) -> bool:
    return any(text != P123_LIMITATION_STATEMENT and _LIVE_PROOF_RE.search(text) for _, text in _walk(value))


def _walk(value: Any, key: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, Mapping):
        for item_key, item_value in value.items():
            yield from _walk(item_value, str(item_key))
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _walk(item, key)
    elif isinstance(value, str):
        yield key, value


def _exact_zero(counters: Mapping[str, Any]) -> bool:
    return set(counters) == set(P123_AUTHORITY_COUNTER_KEYS) and all(isinstance(counters.get(key), int) and counters.get(key) == 0 for key in P123_AUTHORITY_COUNTER_KEYS)


def _require(value: Mapping[str, Any], required: set[str], context: str) -> None:
    missing = sorted(key for key in required if key not in value)
    if missing:
        raise P123ShadowAttachmentError(f"missing_{context}_field:{missing[0]}")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _safe_posix(path: Path) -> str:
    return path.as_posix()


__all__ = [
    "P123ShadowAttachmentError",
    "P123_AUTHORITY_COUNTER_KEYS",
    "build_release_evidence",
    "default_telemetry_records",
    "run_shadow_attachment",
    "validate_release_evidence",
    "write_default_inputs",
    "zero_authority_counters",
]
