#!/usr/bin/env python3
"""Build the P105 reviewed source registry and eligibility manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SUPPORTED_FAMILIES = {"database", "deploy", "queue"}
UNSUPPORTED_FAMILY = "unsupported_family"
REGISTRY_SCHEMA_VERSION = "p105.source-registry.v1"
ELIGIBILITY_SCHEMA_VERSION = "p105.source-eligibility.v1"
LEDGER_SCHEMA_VERSION = "p105.source-review-ledger.v1"
SOURCE_MANIFEST_SCHEMA_VERSION = "p105.reviewed-local-source.v1"
ALLOWED_UNSUPPORTED_REASONS = {
    "unreviewed_source",
    "license_rejected",
    "privacy_rejected",
    "parser_failed",
    "predicate_unmapped",
    "missing_private_ledger",
    "missing_partition",
    "missing_actual_coverage",
    "provenance_mismatch",
    "source_insufficient",
}


class RegistryError(ValueError):
    """Raised when source registry inputs fail closed validation."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RegistryError(f"{label} unreadable: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RegistryError(f"{label} invalid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RegistryError(f"{label} must be a JSON object: {path}")
    return payload


def _require_string(payload: dict[str, Any], key: str, *, context: str, allow_empty: bool = False) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or (not allow_empty and not value):
        raise RegistryError(f"{context} requires string {key}")
    return value


def _require_list(payload: dict[str, Any], key: str, *, context: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise RegistryError(f"{context} requires list {key}")
    return value


def _normalize_path(path: str | Path) -> str:
    return str(Path(path))


def _validate_command_argv(value: Any, *, context: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise RegistryError(f"{context} requires non-empty command_argv")
    return list(value)


def _validate_content_hashes(value: Any, *, context: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise RegistryError(f"{context} requires non-empty source_content_hashes")
    hashes: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise RegistryError(f"{context} source_content_hashes[{index}] must be an object")
        raw_path = _require_string(item, "path", context=f"{context} source_content_hashes[{index}]")
        expected_sha = _require_string(item, "sha256", context=f"{context} source_content_hashes[{index}]")
        path = Path(raw_path)
        if not path.exists():
            raise RegistryError(f"{context} source_content_hashes[{index}] path is missing: {raw_path}")
        actual_sha = _file_sha256(path)
        if actual_sha != expected_sha:
            raise RegistryError(f"{context} source_content_hashes[{index}] sha256 mismatch for {raw_path}")
        hashes.append({"path": _normalize_path(raw_path), "sha256": expected_sha})
    return sorted(hashes, key=lambda item: (item["path"], item["sha256"]))


def _validate_adapter(value: Any, *, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RegistryError(f"{context} requires adapter_or_harness object")
    command_argv = _validate_command_argv(value.get("command_argv"), context=f"{context} adapter_or_harness")
    adapter = {
        "name": _require_string(value, "name", context=f"{context} adapter_or_harness"),
        "version": _require_string(value, "version", context=f"{context} adapter_or_harness"),
        "command_argv": command_argv,
        "command_argv_sha256": _json_sha256(command_argv),
    }
    return adapter


def _validate_license(value: Any, *, context: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise RegistryError(f"{context} requires license object")
    return {
        "name": _require_string(value, "name", context=f"{context} license"),
        "url": _require_string(value, "url", context=f"{context} license"),
        "citation_text": _require_string(value, "citation_text", context=f"{context} license"),
        "redistribution_status": _require_string(value, "redistribution_status", context=f"{context} license"),
    }


def _validate_privacy(value: Any, *, context: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise RegistryError(f"{context} requires privacy object")
    review_status = _require_string(value, "review_status", context=f"{context} privacy")
    if review_status == "reviewed-local":
        reviewer_id = _require_string(value, "reviewer_id", context=f"{context} privacy")
        reviewed_at = _require_string(value, "reviewed_at", context=f"{context} privacy")
        redaction_status = _require_string(value, "redaction_status", context=f"{context} privacy")
    else:
        reviewer_id = str(value.get("reviewer_id") or "")
        reviewed_at = str(value.get("reviewed_at") or "")
        redaction_status = str(value.get("redaction_status") or "")
    return {
        "review_status": review_status,
        "reviewer_id": reviewer_id,
        "reviewed_at": reviewed_at,
        "redaction_status": redaction_status,
        "notes": _require_string(value, "notes", context=f"{context} privacy", allow_empty=True),
    }


def _load_decisions(ledger_path: Path) -> tuple[str, dict[str, dict[str, Any]]]:
    ledger = _read_json(ledger_path, "review ledger")
    if ledger.get("schema_version") != LEDGER_SCHEMA_VERSION:
        raise RegistryError(f"review ledger schema_version must be {LEDGER_SCHEMA_VERSION}")
    decisions_raw = _require_list(ledger, "decisions", context="review ledger")
    decisions: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(decisions_raw):
        if not isinstance(item, dict):
            raise RegistryError(f"review ledger decisions[{index}] must be an object")
        source_key = _require_string(item, "source_key", context=f"review ledger decisions[{index}]")
        if source_key in decisions:
            raise RegistryError(f"review ledger has duplicate source_key decision: {source_key}")
        for key in (
            "reviewer_id",
            "reviewed_at",
            "decision",
            "license_decision",
            "privacy_decision",
            "family_authority_decision",
            "source_manifest_sha256",
            "review_signature_sha256",
        ):
            _require_string(item, key, context=f"review ledger decisions[{index}]")
        decisions[source_key] = item
    return _file_sha256(ledger_path), decisions


def _is_approved(decision: dict[str, Any] | None) -> bool:
    return bool(
        decision
        and decision.get("decision") == "approved"
        and decision.get("license_decision") == "approved"
        and decision.get("privacy_decision") == "approved"
        and decision.get("family_authority_decision") == "approved"
    )


def _noncounting_reason(source_key: str, family: str, decision: dict[str, Any] | None, reviewed: bool) -> str | None:
    if not reviewed or decision is None:
        return "unreviewed_source"
    if decision.get("license_decision") != "approved":
        return "license_rejected"
    if decision.get("privacy_decision") != "approved":
        return "privacy_rejected"
    if not _is_approved(decision):
        return "predicate_unmapped"
    if family == UNSUPPORTED_FAMILY:
        if "parser" in source_key and "failed" in source_key:
            return "parser_failed"
        return "source_insufficient"
    return None


def _registry_source(manifest_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    context = f"source manifest {manifest_path}"
    if manifest.get("schema_version") != SOURCE_MANIFEST_SCHEMA_VERSION:
        raise RegistryError(f"{context} schema_version must be {SOURCE_MANIFEST_SCHEMA_VERSION}")
    missing_metadata: list[str] = []
    if not isinstance(manifest.get("command_argv"), list):
        missing_metadata.append("command_argv")
    privacy_value = manifest.get("privacy")
    if (
        not isinstance(privacy_value, dict)
        or (privacy_value.get("review_status") == "reviewed-local" and not privacy_value.get("reviewer_id"))
    ):
        missing_metadata.append("reviewer_id")
    if missing_metadata:
        raise RegistryError(f"{context} missing required provenance/reviewer metadata: {', '.join(missing_metadata)}")
    source_key = _require_string(manifest, "source_key", context=context)
    family = _require_string(manifest, "source_family_candidate", context=context)
    if family not in SUPPORTED_FAMILIES and family != UNSUPPORTED_FAMILY:
        family = UNSUPPORTED_FAMILY
    source = {
        "source_key": source_key,
        "source_system": _require_string(manifest, "source_system", context=context),
        "source_dataset": _require_string(manifest, "source_dataset", context=context),
        "source_family_candidate": family,
        "source_manifest_path": _normalize_path(manifest_path),
        "source_manifest_sha256": _file_sha256(manifest_path),
        "source_content_hashes": _validate_content_hashes(manifest.get("source_content_hashes"), context=context),
        "adapter_or_harness": _validate_adapter(manifest.get("adapter_or_harness"), context=context),
        "created_at": _require_string(manifest, "created_at", context=context),
        "license": _validate_license(manifest.get("license"), context=context),
        "privacy": _validate_privacy(manifest.get("privacy"), context=context),
    }
    source["provenance_sha256"] = _json_sha256(source)
    _validate_command_argv(manifest.get("command_argv"), context=context)
    return source


def _eligibility_entry(source: dict[str, Any], decision: dict[str, Any] | None) -> dict[str, Any]:
    privacy = source["privacy"]
    reviewed = privacy["review_status"] == "reviewed-local" and bool(privacy["reviewer_id"]) and bool(privacy["reviewed_at"])
    family = str(source["source_family_candidate"])
    reason = _noncounting_reason(str(source["source_key"]), family, decision, reviewed)
    eligible = reason is None and family in SUPPORTED_FAMILIES
    family_candidate = family if eligible else UNSUPPORTED_FAMILY
    entry = {
        "source_key": source["source_key"],
        "source_window_id": source["source_key"],
        "source_manifest_sha256": source["source_manifest_sha256"],
        "materialized_record_sha256": source["provenance_sha256"],
        "pre_label_partition_id": "unpartitioned",
        "family_candidate": family_candidate,
        "family_authority_source": "reviewed_source_registry",
        "eligible_for_release_floor": eligible,
        "unsupported_family_reason": reason,
        "coverage_interval_ids": [],
        "private_ledger_path": "",
        "private_ledger_sha256": "",
        "label_join_phase": "after_sampling_and_partition",
        "adapter_or_parser_version": source["adapter_or_harness"]["version"],
        "privacy_license_registry_sha256": source["provenance_sha256"],
        "counting_rows": 1 if eligible else 0,
        "counting_coverage_seconds": 0,
    }
    if entry["unsupported_family_reason"] is not None and entry["unsupported_family_reason"] not in ALLOWED_UNSUPPORTED_REASONS:
        raise RegistryError(f"unsupported_family_reason is not allowed: {entry['unsupported_family_reason']}")
    entry["provenance_sha256"] = _json_sha256(entry)
    return entry


def build_registry(
    *,
    candidate_manifests: list[Path],
    review_ledger: Path,
    output_registry: Path,
    output_eligibility: Path,
    created_at: str,
    schema_version: str,
    command_argv: list[str],
    fail_on_unreviewed_counting_source: bool,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    if schema_version != REGISTRY_SCHEMA_VERSION:
        raise RegistryError(f"schema_version must be {REGISTRY_SCHEMA_VERSION}")
    ledger_sha256, decisions = _load_decisions(review_ledger)
    errors: list[str] = []
    sources: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []

    for manifest_path in candidate_manifests:
        manifest = _read_json(manifest_path, "source manifest")
        source = _registry_source(manifest_path, manifest)
        source_key = str(source["source_key"])
        decision = decisions.get(source_key)
        if decision is not None and decision["source_manifest_sha256"] != source["source_manifest_sha256"]:
            raise RegistryError(f"source manifest hash mismatch for {source_key}: reviewed metadata was tampered")
        sources.append(source)
        entry = _eligibility_entry(source, decision)
        entries.append(entry)
        if fail_on_unreviewed_counting_source and entry["unsupported_family_reason"] == "unreviewed_source":
            errors.append(f"{source_key}: unreviewed source is unsupported_family and cannot count")

    command_hash = _json_sha256(command_argv)
    sources.sort(key=lambda item: str(item["source_key"]))
    entries.sort(key=lambda item: (str(item["source_key"]), str(item["source_window_id"])))
    registry: dict[str, Any] = {
        "schema_version": schema_version,
        "created_at": created_at,
        "command_argv": command_argv,
        "command_argv_sha256": command_hash,
        "review_ledger_path": _normalize_path(review_ledger),
        "review_ledger_sha256": ledger_sha256,
        "sources": sources,
    }
    registry["registry_sha256"] = _json_sha256(registry)
    eligibility: dict[str, Any] = {
        "schema_version": ELIGIBILITY_SCHEMA_VERSION,
        "created_at": created_at,
        "command_argv": command_argv,
        "command_argv_sha256": command_hash,
        "registry_sha256": registry["registry_sha256"],
        "review_ledger_sha256": ledger_sha256,
        "entries": entries,
        "output_registry_path": _normalize_path(output_registry),
        "output_eligibility_path": _normalize_path(output_eligibility),
    }
    eligibility["eligibility_sha256"] = _json_sha256(eligibility)
    return registry, eligibility, errors


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build P105 reviewed source registry and eligibility manifest")
    parser.add_argument("--candidate-manifest", action="append", required=True, type=Path)
    parser.add_argument("--review-ledger", required=True, type=Path)
    parser.add_argument("--output-registry", required=True, type=Path)
    parser.add_argument("--output-eligibility", required=True, type=Path)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--schema-version", required=True)
    parser.add_argument("--fail-on-unreviewed-counting-source", action="store_true")
    args = parser.parse_args(argv)

    command_argv = [sys.executable, str(Path(__file__)), *(argv if argv is not None else sys.argv[1:])]
    try:
        registry, eligibility, errors = build_registry(
            candidate_manifests=args.candidate_manifest,
            review_ledger=args.review_ledger,
            output_registry=args.output_registry,
            output_eligibility=args.output_eligibility,
            created_at=args.created_at,
            schema_version=args.schema_version,
            command_argv=command_argv,
            fail_on_unreviewed_counting_source=args.fail_on_unreviewed_counting_source,
        )
    except RegistryError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    _write_json(args.output_registry, registry)
    _write_json(args.output_eligibility, eligibility)
    if errors:
        print("; ".join(errors), file=sys.stderr)
        return 1
    print(f"Wrote {args.output_registry}")
    print(f"Wrote {args.output_eligibility}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
