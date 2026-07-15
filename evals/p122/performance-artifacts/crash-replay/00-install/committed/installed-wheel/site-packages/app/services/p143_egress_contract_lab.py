"""Provider-neutral local egress contract lab for P141/P142 artifacts."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.services import p142_loopback_transport_lab as p142
from app.services.p110_evaluation import stable_hash
from app.services.p141_notification_authority import NotificationAuthorityError, list_notification_envelopes, load_notification_config
from app.services.p141_runner import validate_p141_case_matrix
from app.services.p142_runner import p142_release_case_catalog, validate_p142_case_matrix

CONFIG_SCHEMA_VERSION = "p143.egress_contract_config.v1"
INTENT_SCHEMA_VERSION = "p143.egress_intent.v1"
PROJECTION_SCHEMA_VERSION = "p143.provider_projection.v1"
RESULT_SCHEMA_VERSION = "p143.capability_result.v1"
JOURNAL_SCHEMA_VERSION = "p143.replay_journal.v1"
CURSOR_SCHEMA_VERSION = "p143.egress_cursor.v1"
RUN_SCHEMA_VERSION = "p143.egress_run.v1"
PROFILE_SCHEMA_VERSION = "p143.shadow_provider_profile.v1"
EXPECTED_P142_STATUS = "p142_loopback_transport_lab_qualified"
EXPECTED_P142_EVIDENCE_HASH = "sha256:3e952653a335da77ca6ce5f9cc7d6dcb9b39299afc7324c016fe8446f5c7f8e6"
EXPECTED_P141_STATUS = "p141_notification_authority_simulator_qualified"
EXPECTED_P141_EVIDENCE_HASH = "sha256:f3298f1295515b89e5374a449e9deb29fbd70f7c2a1e09446b80d9279d73d3b2"

FORBIDDEN_COUNTER_KEYS: tuple[str, ...] = (
    "credential_read_count",
    "environment_read_count",
    "dns_socket_call_count",
    "proxy_use_count",
    "tls_handshake_count",
    "authentication_attempt_count",
    "redirect_follow_count",
    "provider_sdk_call_count",
    "non_loopback_socket_attempt_count",
    "external_message_send_count",
    "ticket_creation_count",
    "p133_ack_write_count",
    "approval_count",
    "subprocess_shell_count",
    "arbitrary_command_execution_count",
    "action_execution_count",
    "remediation_execution_count",
    "staging_mutation_count",
    "production_mutation_count",
    "operator_replacement_count",
    "authority_escape_count",
    "loopback_socket_attempt_count",
    "loopback_request_commit_count",
    "loopback_request_byte_count",
    "loopback_complete_response_count",
    "loopback_response_byte_count",
    "loopback_retry_count",
    "loopback_transport_failure_count",
    "loopback_http_2xx_count",
    "loopback_http_3xx_count",
    "loopback_http_4xx_count",
    "loopback_http_5xx_count",
    "provider_delivery_attempt_count",
    "provider_auth_material_count",
    "provider_endpoint_parse_count",
    "provider_callback_count",
    "external_http_request_count",
    "external_dns_resolution_count",
)
ALLOWED_COUNTER_KEYS: tuple[str, ...] = (
    "capability_manifest_write_count",
    "compatibility_failure_count",
    "intent_projection_count",
    "replay_journal_entry_count",
    "schema_rejection_count",
    "shadow_provider_validation_count",
)
_MEASURED_ALLOWED_COUNTERS: dict[str, int] = {key: 0 for key in ALLOWED_COUNTER_KEYS}
_CONFIG_FIELDS = frozenset(
    {
        "schema_version",
        "lab_id",
        "immutable_read_roots",
        "p141_config_path",
        "p142_config_path",
        "p142_release_evidence_path",
        "shadow_profile_path",
        "intent_dir",
        "projection_dir",
        "result_dir",
        "journal_dir",
        "cursor_path",
        "run_dir",
        "max_sources_per_run",
        "max_profiles_per_source",
        "max_projection_bytes",
        "max_evidence_refs",
        "max_artifact_files",
        "max_total_bytes",
        "min_artifact_free_bytes",
    }
)
_FORBIDDEN_FIELD_WORDS = frozenset(
    {
        "auth",
        "credential",
        "deliver",
        "dns",
        "endpoint",
        "header",
        "proxy",
        "provider",
        "provider_sdk",
        "secret",
        "send",
        "tls",
        "token",
        "url",
        "webhook",
    }
)
_UNSAFE_VALUE_RE = re.compile(r"(?:https?://|wss?://|\$\{|\b(?:auth|credential|endpoint|secret|token|webhook)\b)", re.IGNORECASE)
_LABEL_RE = re.compile(r"[a-z0-9][a-z0-9_.:-]{0,63}\Z")
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_UTC_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)\Z")
_CHANNELS = frozenset({"chat_message", "email_message", "pager_event", "incident_comment"})
_TRANSITION_SEVERITY = {"opened": "critical", "updated": "warning", "reminder": "info", "recovered": "recovered"}
_PHASES = (
    "validated_source",
    "intent_prepared",
    "intent_written",
    "projection_prepared",
    "projection_written",
    "capability_result_prepared",
    "capability_result_written",
    "run_prepared",
    "cursor_written",
    "run_written",
)


class EgressContractError(ValueError):
    """Raised when P143 cannot prove its local provider-neutral boundary."""


@dataclass(frozen=True)
class EgressContractConfig:
    schema_version: str
    config_hash: str
    lab_id: str
    immutable_read_roots: tuple[Path, ...]
    p141_config_path: Path
    p142_config_path: Path
    p142_release_evidence_path: Path
    shadow_profile_path: Path
    intent_dir: Path
    projection_dir: Path
    result_dir: Path
    journal_dir: Path
    cursor_path: Path
    run_dir: Path
    lease_path: Path
    writable_roots: tuple[Path, ...]
    max_sources_per_run: int
    max_profiles_per_source: int
    max_projection_bytes: int
    max_evidence_refs: int
    max_artifact_files: int
    max_total_bytes: int
    min_artifact_free_bytes: int


def canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def zero_forbidden_counters() -> dict[str, int]:
    return {key: 0 for key in FORBIDDEN_COUNTER_KEYS}


def zero_allowed_counters() -> dict[str, int]:
    return {key: 0 for key in ALLOWED_COUNTER_KEYS}


def reset_measured_allowed_counters() -> None:
    _MEASURED_ALLOWED_COUNTERS.update(zero_allowed_counters())


def record_measured_allowed_counters(counters: Mapping[str, Any]) -> None:
    if not _exact_counter_map(counters, ALLOWED_COUNTER_KEYS, exact_zero=False):
        raise EgressContractError("allowed_counters_invalid")
    _MEASURED_ALLOWED_COUNTERS.update({key: int(counters[key]) for key in ALLOWED_COUNTER_KEYS})


def measured_allowed_counters() -> dict[str, int]:
    return dict(_MEASURED_ALLOWED_COUNTERS)


def load_egress_contract_config(path: Path | str) -> EgressContractConfig:
    config_path = _absolute(_literal_path(path, "configuration_path"))
    _reject_symlink_components(config_path)
    _regular_file_stat(config_path, "configuration")
    raw = _read_json(config_path, "configuration")
    if set(raw) != _CONFIG_FIELDS:
        unknown = set(raw) - _CONFIG_FIELDS
        if any(_field_forbidden(item) for item in unknown):
            raise EgressContractError("forbidden_configuration_field")
        raise EgressContractError("invalid_configuration_fields")
    if raw.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise EgressContractError("invalid_configuration_schema")
    _reject_unsafe_values(raw)
    base = config_path.parent
    read_roots = tuple(_resolve(base, item) for item in _sequence(raw["immutable_read_roots"], "immutable_read_roots"))
    p141_config_path = _resolve(base, raw["p141_config_path"])
    p142_config_path = _resolve(base, raw["p142_config_path"])
    p142_release_evidence_path = _resolve(base, raw["p142_release_evidence_path"])
    shadow_profile_path = _resolve(base, raw["shadow_profile_path"])
    intent_dir = _resolve(base, raw["intent_dir"])
    projection_dir = _resolve(base, raw["projection_dir"])
    result_dir = _resolve(base, raw["result_dir"])
    journal_dir = _resolve(base, raw["journal_dir"])
    cursor_path = _resolve(base, raw["cursor_path"])
    run_dir = _resolve(base, raw["run_dir"])
    lease_path = cursor_path.with_name(f".{cursor_path.name}.lock")
    path_candidates = (
        p141_config_path,
        p142_config_path,
        p142_release_evidence_path,
        shadow_profile_path,
        *read_roots,
        intent_dir,
        projection_dir,
        result_dir,
        journal_dir,
        cursor_path,
        run_dir,
        lease_path,
    )
    for candidate in path_candidates:
        _reject_symlink_components(candidate)
    for readable in (p141_config_path, p142_config_path, p142_release_evidence_path, shadow_profile_path):
        _regular_file_stat(readable, "dependency")
    for root in read_roots:
        if not root.is_dir():
            raise EgressContractError("immutable_read_root_missing")
        _require_safe_directory(root, "immutable_read_root")
    writable_roots = _distinct_roots((intent_dir, projection_dir, result_dir, journal_dir, cursor_path, run_dir))
    if any(_overlaps(read_root, write_root) for read_root in read_roots for write_root in writable_roots):
        raise EgressContractError("read_write_root_overlap")
    for root in writable_roots:
        root.mkdir(parents=True, exist_ok=True)
        _require_safe_directory(root, "writable_root")
    _require_distinct_output_paths(intent_dir, projection_dir, result_dir, journal_dir, cursor_path, run_dir, lease_path)
    budget_keys = (
        "max_sources_per_run",
        "max_profiles_per_source",
        "max_projection_bytes",
        "max_evidence_refs",
        "max_artifact_files",
        "max_total_bytes",
        "min_artifact_free_bytes",
    )
    budgets = {key: _bounded_int(raw, key) for key in budget_keys}
    return EgressContractConfig(
        schema_version=CONFIG_SCHEMA_VERSION,
        config_hash=stable_hash(raw),
        lab_id=_safe_label(raw["lab_id"], "lab_id"),
        immutable_read_roots=read_roots,
        p141_config_path=p141_config_path,
        p142_config_path=p142_config_path,
        p142_release_evidence_path=p142_release_evidence_path,
        shadow_profile_path=shadow_profile_path,
        intent_dir=intent_dir,
        projection_dir=projection_dir,
        result_dir=result_dir,
        journal_dir=journal_dir,
        cursor_path=cursor_path,
        run_dir=run_dir,
        lease_path=lease_path,
        writable_roots=writable_roots,
        **budgets,
    )


def validate_egress_contract_config(config: EgressContractConfig) -> dict[str, Any]:
    _validate_p142_release(config)
    profile = _load_profile(config)
    return {"status": "valid", "lab_id": config.lab_id, "config_hash": config.config_hash, "profile_channel_count": len(profile["channels"])}


def process_egress_contracts(
    config: EgressContractConfig,
    *,
    monotonic: Any | None = None,
    wall_clock: Any | None = None,
    crash_after: str | None = None,
) -> dict[str, Any]:
    _ = monotonic, wall_clock
    with _Lease(config):
        _ensure_output_dirs(config)
        journals = _load_all_journals(config)
        existing_runs = sorted(config.run_dir.glob("*.json"))
        _validate_existing_artifacts(config, journals)
        _validate_p142_release(config)
        profile = _load_profile(config)
        sources = _load_sources(config)
        _validate_expected_artifact_graph(config, profile, sources, journals)
        recovered, recovery_performed = _recover_prepared_run(config, journals, existing_runs)
        if recovery_performed and recovered is not None:
            recovered_journals = _load_all_journals(config)
            _validate_existing_artifacts(config, recovered_journals)
            _validate_expected_artifact_graph(config, profile, sources, recovered_journals)
            _validate_run_counter_bindings(config, recovered, recovered_journals)
            record_measured_allowed_counters(recovered["allowed_counters"])
            return recovered
        pre_cursor_recovery = _recover_prepared_run_before_cursor(config, journals, sources)
        if pre_cursor_recovery is not None:
            recovered_journals = _load_all_journals(config)
            _validate_existing_artifacts(config, recovered_journals)
            _validate_expected_artifact_graph(config, profile, sources, recovered_journals)
            _validate_run_counter_bindings(config, pre_cursor_recovery, recovered_journals)
            record_measured_allowed_counters(pre_cursor_recovery["allowed_counters"])
            return pre_cursor_recovery
        pending_sources = _sources_after_cursor(config, sources)
        if not pending_sources:
            if recovered is None:
                raise EgressContractError("completed_run_missing")
            completed_journals = _load_all_journals(config)
            _validate_existing_artifacts(config, completed_journals)
            _validate_expected_artifact_graph(config, profile, sources, completed_journals)
            _validate_run_counter_bindings(config, recovered, completed_journals)
            record_measured_allowed_counters(recovered["allowed_counters"])
            return recovered
        selected_sources = pending_sources[: config.max_sources_per_run]
        for source in selected_sources:
            source_id = source["source_id"]
            journal = _load_or_new_journal(config, source_id)
            _append_journal(
                config,
                journal,
                "validated_source",
                {"source_id": source_id, "profile_hash": stable_hash(profile)},
            )
            envelope = source["envelope"]
            receipt = source["receipt"]
            intent = build_egress_intent(config, envelope, receipt)
            _prepare_artifact(config, journal, "intent_prepared", "intent", intent)
            if crash_after == "intent_prepared":
                raise RuntimeError("injected_crash:intent_prepared")
            _write_bound_artifact(
                config.intent_dir / f"{intent['intent_id'][7:]}.json",
                intent,
                config,
                "intent",
                crash_after=crash_after,
            )
            _append_journal(config, journal, "intent_written", {"intent_hash": intent["intent_hash"]})
            for channel in profile["channels"][: config.max_profiles_per_source]:
                projection = project_shadow_provider(intent, channel)
                if len(canonical_json(projection)) > config.max_projection_bytes:
                    raise EgressContractError("projection_size_exceeded")
                _prepare_artifact(config, journal, "projection_prepared", "projection", projection)
                if crash_after == "projection_prepared":
                    raise RuntimeError("injected_crash:projection_prepared")
                _write_bound_artifact(
                    config.projection_dir / f"{projection['projection_id'][7:]}.json",
                    projection,
                    config,
                    "projection",
                    crash_after=crash_after,
                )
                _append_journal(config, journal, "projection_written", {"projection_hash": projection["projection_hash"]})
                result = evaluate_shadow_capability(projection, channel)
                _prepare_artifact(config, journal, "capability_result_prepared", "result", result)
                _write_bound_artifact(
                    config.result_dir / f"{result['result_id'][7:]}.json",
                    result,
                    config,
                    "result",
                    crash_after=crash_after,
                )
                _append_journal(config, journal, "capability_result_written", {"result_hash": result["result_hash"]})
        if crash_after == "result:before_cursor":
            raise RuntimeError("injected_crash:result:before_cursor")
        cursor = _cursor(config, selected_sources[-1] if selected_sources else None)
        counters = _artifact_allowed_counters(
            config,
            _load_all_journals(config),
            anticipated_terminal_source_ids={str(source["source_id"]) for source in selected_sources},
        )
        source_bindings = [
            _expected_source_artifacts(config, source, profile)[3]
            for source in selected_sources
        ]
        run = _build_run(
            config,
            profile_hash=stable_hash(profile),
            source_bindings=source_bindings,
            counters=counters,
        )
        for source in selected_sources:
            journal = _load_or_new_journal(config, source["source_id"])
            _prepare_artifact(config, journal, "run_prepared", "run", run)
        if crash_after == "run_prepared":
            raise RuntimeError("injected_crash:run_prepared")
        _atomic_write_json(
            config.cursor_path,
            cursor,
            config.writable_roots,
            artifact_kind="cursor",
            crash_after=crash_after,
        )
        for source in selected_sources:
            journal = _load_or_new_journal(config, source["source_id"])
            _append_journal(config, journal, "cursor_written", {"cursor_hash": cursor["cursor_hash"]})
        if crash_after == "cursor_written":
            raise RuntimeError("injected_crash:cursor_written")
        _atomic_write_json(
            config.run_dir / f"{run['run_hash'][7:]}.json",
            run,
            config.writable_roots,
            artifact_kind="run",
            crash_after=crash_after,
        )
        if crash_after == "run_published":
            raise RuntimeError("injected_crash:run_published")
        for source in selected_sources:
            journal = _load_or_new_journal(config, source["source_id"])
            _append_journal(config, journal, "run_written", {"run_hash": run["run_hash"]})
        completed_journals = _load_all_journals(config)
        _validate_existing_artifacts(config, completed_journals)
        _validate_expected_artifact_graph(config, profile, sources, completed_journals)
        _validate_run_counter_bindings(config, run, completed_journals)
        record_measured_allowed_counters(run["allowed_counters"])
        return run


def list_egress_results(config: EgressContractConfig) -> list[dict[str, Any]]:
    if not config.result_dir.exists():
        return []
    values = [_read_json(path, "result") for path in sorted(config.result_dir.glob("*.json"))]
    for value in values:
        _validate_result(value)
    return values


def build_egress_intent(config: EgressContractConfig, envelope: Mapping[str, Any], loopback_receipt: Mapping[str, Any]) -> dict[str, Any]:
    _validate_envelope(envelope)
    _validate_receipt(loopback_receipt)
    binding = loopback_receipt["p141_binding"]
    if binding["envelope_id"] != envelope["envelope_id"]:
        raise EgressContractError("dependency_graph_invalid")
    transition = str(envelope["source_event"]["transition_kind"])
    if transition not in _TRANSITION_SEVERITY:
        raise EgressContractError("unsupported_transition_kind")
    evidence_refs = list(envelope["message"].get("evidence_refs", []))
    base = {
        "config_hash": config.config_hash,
        "envelope_hash": envelope["envelope_hash"],
        "receipt_hash": loopback_receipt["receipt_hash"],
        "destination_id": envelope["destination_id"],
        "transition_kind": transition,
    }
    intent_id = stable_hash({"p143_intent": base})
    intent = {
        "schema_version": INTENT_SCHEMA_VERSION,
        "intent_id": intent_id,
        "config_hash": config.config_hash,
        "envelope_id": envelope["envelope_id"],
        "envelope_hash": envelope["envelope_hash"],
        "loopback_receipt_hash": loopback_receipt["receipt_hash"],
        "destination_id": envelope["destination_id"],
        "transition_kind": transition,
        "severity": _TRANSITION_SEVERITY[transition],
        "title": str(envelope["message"]["title"]),
        "body": str(envelope["message"]["summary"]),
        "evidence_refs": evidence_refs,
        "idempotency_key": stable_hash({"p143_idempotency": base}),
        "dedupe_key": stable_hash({"p143_dedupe": {"incident_id": envelope["source_event"]["incident_id"], "destination_id": envelope["destination_id"], "transition_kind": transition}}),
    }
    intent["intent_hash"] = stable_hash(intent)
    _validate_intent(intent)
    return intent


def project_shadow_provider(intent: Mapping[str, Any], profile: Mapping[str, Any]) -> dict[str, Any]:
    _validate_intent(intent)
    channel = _validate_channel(profile)
    title, title_truncated = _truncate(str(intent["title"]), int(channel["max_title_chars"]))
    body, body_truncated = _truncate(str(intent["body"]), int(channel["max_body_chars"]))
    projection = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "projection_id": stable_hash({"intent_hash": intent["intent_hash"], "channel_type": channel["channel_type"]}),
        "intent_id": intent["intent_id"],
        "intent_hash": intent["intent_hash"],
        "channel_type": channel["channel_type"],
        "payload": {
            "title": title,
            "body": body,
            "severity": intent["severity"],
            "idempotency_key": intent["idempotency_key"],
            "dedupe_key": intent["dedupe_key"],
            "evidence_refs": list(intent["evidence_refs"]),
        },
        "truncation": {"title_truncated": title_truncated, "body_truncated": body_truncated},
        "rate_limit": {"policy": channel["rate_limit_policy"], "wait_performed": False},
    }
    projection["projection_hash"] = stable_hash(projection)
    return projection


def evaluate_shadow_capability(projection: Mapping[str, Any], profile: Mapping[str, Any]) -> dict[str, Any]:
    channel = _validate_channel(profile)
    payload = projection.get("payload")
    if not isinstance(payload, Mapping):
        raise EgressContractError("invalid_projection_payload")
    reasons: list[str] = []
    for field in channel["required_fields"]:
        if field not in payload or payload[field] in ("", None):
            reasons.append(f"missing_required:{field}")
    if channel["supports_idempotency"] is not True:
        reasons.append("idempotency_not_supported")
    if channel["supports_dedupe"] is not True:
        reasons.append("dedupe_not_supported")
    if len(str(payload.get("body", ""))) >= int(channel["max_body_chars"]) and projection.get("truncation", {}).get("body_truncated") is True:
        reasons.append("payload_size_limit_exceeded")
    if len(payload.get("evidence_refs", [])) > int(channel["max_evidence_refs"]):
        reasons.append("evidence_ref_limit_exceeded")
    result = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "result_id": stable_hash({"projection_hash": projection["projection_hash"], "channel_type": channel["channel_type"]}),
        "projection_id": projection["projection_id"],
        "projection_hash": projection["projection_hash"],
        "channel_type": channel["channel_type"],
        "compatible": not reasons,
        "reasons": reasons,
        "retry_classification": "local_no_retry",
        "rate_limit_manifest_only": projection.get("rate_limit") == {"policy": "manifest_only", "wait_performed": False},
    }
    result["result_hash"] = stable_hash(result)
    _validate_result(result)
    return result


def _load_sources(config: EgressContractConfig) -> list[dict[str, Any]]:
    p141_config = load_notification_config(config.p141_config_path)
    p142_config = p142.load_loopback_transport_config(config.p142_config_path)
    try:
        envelope_values = list_notification_envelopes(p141_config)
    except NotificationAuthorityError as exc:
        if str(exc) in {"envelope_contract_invalid", "envelope_hash_invalid"}:
            raise EgressContractError("p141_envelope_hash_invalid") from exc
        raise EgressContractError("dependency_graph_invalid") from exc
    except Exception as exc:
        raise EgressContractError("dependency_graph_invalid") from exc
    envelopes = {value["envelope_hash"]: value for value in envelope_values}
    if not envelopes:
        raise EgressContractError("envelope_missing")
    receipts = [_read_json(path, "receipt") for path in sorted(p142_config.receipt_dir.glob("*.json"))]
    dispatch_values = [_read_json(path, "dispatch") for path in sorted(p142_config.dispatch_dir.glob("*.json"))]
    journal_values = [_read_json(path, "journal") for path in sorted(p142_config.journal_dir.glob("*.json"))]
    dispatches = _unique_by(dispatch_values, "dispatch_id")
    journals = _unique_by(journal_values, "dispatch_id")
    receipt_ids = [receipt.get("dispatch_id") for receipt in receipts]
    if len(set(receipt_ids)) != len(receipt_ids) or set(receipt_ids) != set(dispatches) or set(receipt_ids) != set(journals):
        raise EgressContractError("dependency_graph_invalid")
    sources: list[dict[str, Any]] = []
    for receipt in receipts:
        _validate_receipt(receipt)
        binding = receipt["p141_binding"]
        envelope = envelopes.get(binding["envelope_hash"])
        if envelope is None:
            raise EgressContractError("envelope_missing")
        _validate_envelope(envelope)
        dispatch = dispatches.get(receipt["dispatch_id"])
        journal = journals.get(receipt["dispatch_id"])
        if dispatch is None or journal is None:
            raise EgressContractError("dependency_graph_invalid")
        _validate_dispatch_receipt_journal(p142_config, dispatch, receipt, journal, envelope)
        sources.append({"source_id": stable_hash({"receipt_hash": receipt["receipt_hash"]}), "envelope": envelope, "receipt": receipt})
    return sources


def _validate_p142_release(config: EgressContractConfig) -> None:
    evidence = _read_json(config.p142_release_evidence_path, "p142_release_evidence")
    if evidence.get("evidence_hash") != stable_hash({key: value for key, value in evidence.items() if key != "evidence_hash"}):
        raise EgressContractError("p142_release_evidence_hash_invalid")
    if evidence.get("status") != EXPECTED_P142_STATUS or evidence.get("evidence_hash") != EXPECTED_P142_EVIDENCE_HASH:
        raise EgressContractError("p142_release_dependency_drift")
    p141 = evidence.get("p141_dependency")
    if not isinstance(p141, Mapping) or p141.get("p141_evidence_hash") != EXPECTED_P141_EVIDENCE_HASH:
        raise EgressContractError("p142_p141_dependency_drift")
    try:
        _validate_frozen_p142_dependency(config, evidence)
    except EgressContractError:
        raise
    except Exception as exc:
        raise EgressContractError("dependency_graph_invalid") from exc


def _validate_frozen_p142_dependency(config: EgressContractConfig, evidence: Mapping[str, Any]) -> None:
    p142_root = config.p142_release_evidence_path.parent.parent
    if config.p142_release_evidence_path.name != "release-evidence.json" or p142_root.name != "p142":
        raise EgressContractError("dependency_graph_invalid")
    eval_root = p142_root.parent
    freeze = _read_json(p142_root / "output/freeze-manifest.json", "p142_freeze_manifest")
    matrix = _read_json(p142_root / "output/canonical-matrix.json", "p142_matrix")
    review = _read_json(p142_root / "final-implementation-review.json", "p142_final_review")
    profile = _read_json(p142_root / "input/loopback-transport-lab-profile.json", "p142_profile")
    _require_self_hash(freeze, "freeze_manifest_hash")
    _require_self_hash(review, "review_hash")
    validated_matrix = validate_p142_case_matrix(matrix)
    if set(profile) != {"schema_version", "cases"} or profile.get("schema_version") != "p142.loopback_transport_lab_profile.v1":
        raise EgressContractError("dependency_graph_invalid")
    if profile.get("cases") != p142_release_case_catalog():
        raise EgressContractError("dependency_graph_invalid")
    expected_release_bindings = {
        "matrix_hash": validated_matrix["matrix_hash"],
        "freeze_manifest_hash": freeze["freeze_manifest_hash"],
        "final_review_hash": review["review_hash"],
    }
    if any(evidence.get(key) != value for key, value in expected_release_bindings.items()):
        raise EgressContractError("dependency_graph_invalid")
    if freeze.get("matrix_hash") != validated_matrix["matrix_hash"] or freeze.get("profile_hash") != stable_hash(profile):
        raise EgressContractError("dependency_graph_invalid")
    profile_path = "evals/p142/input/loopback-transport-lab-profile.json"
    if freeze.get("source_bindings", {}).get(profile_path) != _file_sha256(p142_root / "input/loopback-transport-lab-profile.json"):
        raise EgressContractError("dependency_graph_invalid")
    review_bindings = {
        "approved_plan_sha256": freeze.get("approved_plan_sha256"),
        "reviewed_test_spec_sha256": freeze.get("approved_test_spec_sha256"),
        "reviewed_plan_review_sha256": freeze.get("plan_review_sha256"),
        "reviewed_profile_hash": freeze.get("profile_hash"),
        "reviewed_matrix_hash": freeze.get("matrix_hash"),
        "reviewed_freeze_manifest_hash": freeze.get("freeze_manifest_hash"),
        "reviewed_source_hashes": freeze.get("source_bindings"),
        "reviewed_dependency_bindings": freeze.get("dependency_bindings"),
    }
    if any(review.get(key) != value for key, value in review_bindings.items()):
        raise EgressContractError("dependency_graph_invalid")
    p141_binding = evidence.get("p141_dependency")
    if p141_binding != freeze.get("dependency_bindings") or review.get("reviewed_dependency_bindings") != p141_binding:
        raise EgressContractError("dependency_graph_invalid")
    _validate_frozen_p141_p133(eval_root, p141_binding)


def _validate_frozen_p141_p133(eval_root: Path, binding: Any) -> None:
    if not isinstance(binding, Mapping):
        raise EgressContractError("dependency_graph_invalid")
    p141_root = eval_root / "p141"
    release = _read_json(p141_root / "output/release-evidence.json", "p141_release_evidence")
    freeze = _read_json(p141_root / "output/freeze-manifest.json", "p141_freeze_manifest")
    matrix = _read_json(p141_root / "output/canonical-matrix.json", "p141_matrix")
    review = _read_json(p141_root / "final-implementation-review.json", "p141_final_review")
    p133 = _read_json(eval_root / "p133/release-evidence.json", "p133_release_evidence")
    _require_self_hash(release, "evidence_hash")
    _require_self_hash(freeze, "freeze_manifest_hash")
    _require_self_hash(review, "review_hash")
    _require_self_hash(p133, "release_evidence_hash")
    validated_matrix = validate_p141_case_matrix(matrix)
    expected = {
        "p141_status": release.get("status"),
        "p141_evidence_hash": release.get("evidence_hash"),
        "p141_matrix_hash": validated_matrix.get("matrix_hash"),
        "p141_freeze_manifest_hash": freeze.get("freeze_manifest_hash"),
        "p141_final_review_hash": review.get("review_hash"),
    }
    if dict(binding) != expected or release.get("status") != EXPECTED_P141_STATUS or release.get("evidence_hash") != EXPECTED_P141_EVIDENCE_HASH:
        raise EgressContractError("dependency_graph_invalid")
    if release.get("matrix_hash") != validated_matrix.get("matrix_hash") or release.get("freeze_manifest_hash") != freeze.get("freeze_manifest_hash"):
        raise EgressContractError("dependency_graph_invalid")
    if release.get("final_review_hash") != review.get("review_hash") or review.get("reviewed_freeze_manifest_hash") != freeze.get("freeze_manifest_hash"):
        raise EgressContractError("dependency_graph_invalid")
    dependencies = freeze.get("dependency_bindings")
    if review.get("reviewed_dependency_bindings") != dependencies or not isinstance(dependencies, Mapping):
        raise EgressContractError("dependency_graph_invalid")
    if dependencies.get("p133_status") != p133.get("release_status") or dependencies.get("p133_evidence_hash") != p133.get("release_evidence_hash"):
        raise EgressContractError("dependency_graph_invalid")


def _validate_dispatch_receipt_journal(
    p142_config: Any,
    dispatch: Mapping[str, Any],
    receipt: Mapping[str, Any],
    journal: Mapping[str, Any],
    envelope: Mapping[str, Any],
) -> None:
    try:
        p142._validate_dispatch_record(dispatch, p142_config.config_hash)
        p142._validate_journal(journal, str(dispatch["dispatch_id"]), p142_config.config_hash)
        p142._validate_receipt(receipt)
        p142._validate_replayed_receipt_binding(p142_config, dispatch, journal, receipt)
        route = next(item for item in p142_config.routes if item.route_id == dispatch["route_id"])
        request_body = p142._request_body(envelope, route)
        request_hash = "sha256:" + hashlib.sha256(request_body).hexdigest()
        expected_dispatch_id = p142.deterministic_dispatch_id(
            p142_config.config_hash,
            str(envelope["envelope_hash"]),
            route.destination_id,
            route.route_id,
            route.method,
            route.authority,
            route.path,
            request_hash,
        )
        if dispatch.get("dispatch_id") != expected_dispatch_id or dispatch.get("request_body_hash") != request_hash:
            raise EgressContractError("dependency_graph_invalid")
        expected_dispatch_bindings = {
            "envelope_id": envelope["envelope_id"],
            "envelope_hash": envelope["envelope_hash"],
            "source_event_hash": envelope["source_event"]["event_hash"],
            "destination_id": envelope["destination_id"],
            "config_hash": p142_config.config_hash,
        }
        if any(dispatch.get(key) != value for key, value in expected_dispatch_bindings.items()):
            raise EgressContractError("dependency_graph_invalid")
        entries = journal["entries"]
        terminal = entries[-1]
        phases = tuple(terminal["phases"])
        if "response" in terminal:
            expected_receipt = p142._receipt_from_response(p142_config, dispatch, entries, terminal["response"])
        elif phases == ("pre_socket", "request_committed"):
            expected_receipt = p142._receipt_from_unknown(p142_config, dispatch, entries)
        else:
            expected_receipt = p142._receipt_from_failure(
                p142_config,
                dispatch,
                entries,
                str(receipt["failure_class"]),
                receipt["transport_counters"],
            )
        if dict(receipt) != expected_receipt or receipt.get("production_delivered") is not False:
            raise EgressContractError("dependency_graph_invalid")
    except EgressContractError:
        raise
    except Exception as exc:
        raise EgressContractError("dependency_graph_invalid") from exc


def _unique_by(values: list[dict[str, Any]], key: str) -> dict[Any, dict[str, Any]]:
    result: dict[Any, dict[str, Any]] = {}
    for value in values:
        identity = value.get(key)
        if identity in result:
            raise EgressContractError("dependency_graph_invalid")
        result[identity] = value
    return result


def _require_self_hash(value: Mapping[str, Any], field: str) -> None:
    if value.get(field) != stable_hash({key: item for key, item in value.items() if key != field}):
        raise EgressContractError("dependency_graph_invalid")


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_envelope(value: Mapping[str, Any]) -> None:
    if value.get("envelope_hash") != stable_hash({key: item for key, item in value.items() if key != "envelope_hash"}):
        raise EgressContractError("p141_envelope_hash_invalid")


def _validate_receipt(value: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "config_hash",
        "p141_binding",
        "dispatch_id",
        "attempt_ids",
        "numeric_loopback_authority",
        "method",
        "path",
        "request_body_hash",
        "status_code",
        "failure_class",
        "response_body_hash",
        "response_truncated",
        "retry_after",
        "timing_budget",
        "retry_schedule",
        "delivered_to_loopback",
        "production_delivered",
        "acknowledged",
        "authority_counters",
        "transport_counters",
        "receipt_hash",
    }
    if set(value) != required:
        raise EgressContractError("invalid_receipt_fields")
    if value.get("production_delivered") is not False or value.get("acknowledged") is not False:
        raise EgressContractError("receipt_authority_invalid")
    if value.get("receipt_hash") != stable_hash({key: item for key, item in value.items() if key != "receipt_hash"}):
        raise EgressContractError("receipt_hash_invalid")


def _validate_intent(value: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "intent_id",
        "config_hash",
        "envelope_id",
        "envelope_hash",
        "loopback_receipt_hash",
        "destination_id",
        "transition_kind",
        "severity",
        "title",
        "body",
        "evidence_refs",
        "idempotency_key",
        "dedupe_key",
        "intent_hash",
    }
    if set(value) != required or value.get("schema_version") != INTENT_SCHEMA_VERSION:
        raise EgressContractError("invalid_intent_schema")
    for key in ("intent_id", "config_hash", "envelope_hash", "loopback_receipt_hash", "idempotency_key", "dedupe_key", "intent_hash"):
        _hash_value(value[key], key)
    if value.get("intent_hash") != stable_hash({key: item for key, item in value.items() if key != "intent_hash"}):
        raise EgressContractError("intent_hash_invalid")


def _validate_result(value: Mapping[str, Any]) -> None:
    if value.get("schema_version") != RESULT_SCHEMA_VERSION:
        raise EgressContractError("invalid_result_schema")
    if value.get("result_hash") != stable_hash({key: item for key, item in value.items() if key != "result_hash"}):
        raise EgressContractError("result_hash_invalid")


def _validate_run(value: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "lab_id",
        "config_hash",
        "profile_hash",
        "source_batch_hash",
        "processed_source_count",
        "result_count",
        "replayed_source_count",
        "forbidden_counters",
        "allowed_counters",
        "generated_at",
        "run_hash",
    }
    if set(value) != required or value.get("schema_version") != RUN_SCHEMA_VERSION:
        raise EgressContractError("invalid_run_schema")
    for key in ("config_hash", "profile_hash", "source_batch_hash", "run_hash"):
        _hash_value(value.get(key), key)
    for key in ("processed_source_count", "result_count", "replayed_source_count"):
        if type(value.get(key)) is not int or value[key] < 0:
            raise EgressContractError("invalid_run_count")
    if not _exact_counter_map(value.get("forbidden_counters"), FORBIDDEN_COUNTER_KEYS, exact_zero=True):
        raise EgressContractError("forbidden_counters_invalid")
    if not _exact_counter_map(value.get("allowed_counters"), ALLOWED_COUNTER_KEYS, exact_zero=False):
        raise EgressContractError("allowed_counters_invalid")
    if value.get("run_hash") != stable_hash({key: item for key, item in value.items() if key != "run_hash"}):
        raise EgressContractError("run_hash_invalid")


def _load_profile(config: EgressContractConfig) -> dict[str, Any]:
    profile = _read_json(config.shadow_profile_path, "shadow_profile")
    if profile.get("schema_version") != PROFILE_SCHEMA_VERSION or not isinstance(profile.get("channels"), list):
        raise EgressContractError("invalid_shadow_profile")
    for channel in profile["channels"]:
        _validate_channel(channel)
    return profile


def _validate_channel(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {"channel_type", "required_fields", "max_title_chars", "max_body_chars", "max_evidence_refs", "supports_idempotency", "supports_dedupe", "rate_limit_policy"}
    if set(value) != required:
        raise EgressContractError("invalid_channel_profile")
    if value["channel_type"] not in _CHANNELS:
        raise EgressContractError("unsupported_channel_type")
    if value["rate_limit_policy"] != "manifest_only":
        raise EgressContractError("invalid_rate_limit_policy")
    for key in ("max_title_chars", "max_body_chars", "max_evidence_refs"):
        if type(value[key]) is not int or value[key] <= 0:
            raise EgressContractError("invalid_channel_limit")
    return dict(value)


def _truncate(value: str, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    if limit <= 12:
        return value[:limit], True
    suffix = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"{value[: limit - 9]}#{suffix}", True


def _load_or_new_journal(config: EgressContractConfig, source_id: str) -> dict[str, Any]:
    path = config.journal_dir / f"{source_id[7:]}.json"
    if path.exists():
        value = _read_json(path, "journal")
        _validate_replay_journal(value, source_id)
        return value
    journal: dict[str, Any] = {"schema_version": JOURNAL_SCHEMA_VERSION, "source_id": source_id, "entries": []}
    journal["journal_hash"] = stable_hash(journal)
    _atomic_write_json(path, journal, config.writable_roots)
    return journal


def _append_journal(config: EgressContractConfig, journal: dict[str, Any], phase: str, data: Mapping[str, Any]) -> int:
    if phase not in _PHASES:
        raise EgressContractError("invalid_journal_phase")
    entries = list(journal["entries"])
    canonical_data = dict(data)
    if any(entry.get("phase") == phase and entry.get("data") == canonical_data for entry in entries):
        return 0
    if phase in {"validated_source", "intent_prepared", "intent_written", "run_prepared", "cursor_written", "run_written"} and any(
        entry.get("phase") == phase for entry in entries
    ):
        raise EgressContractError("conflicting_replay_journal_entry")
    entries.append({"ordinal": len(entries), "phase": phase, "data": canonical_data})
    journal.update({"entries": entries})
    journal["journal_hash"] = stable_hash({key: item for key, item in journal.items() if key != "journal_hash"})
    _validate_replay_journal(journal, str(journal["source_id"]))
    _atomic_write_json(config.journal_dir / f"{journal['source_id'][7:]}.json", journal, config.writable_roots)
    return 1


def _prepare_artifact(config: EgressContractConfig, journal: dict[str, Any], phase: str, kind: str, value: Mapping[str, Any]) -> None:
    _append_journal(
        config,
        journal,
        phase,
        {kind: dict(value), "byte_sha256": "sha256:" + hashlib.sha256(canonical_json(value) + b"\n").hexdigest()},
    )


def _write_bound_artifact(
    path: Path,
    value: Mapping[str, Any],
    config: EgressContractConfig,
    kind: str,
    *,
    crash_after: str | None = None,
) -> None:
    if path.exists():
        if path.read_bytes() != canonical_json(value) + b"\n":
            raise EgressContractError("conflicting_replay_artifact")
        return
    _atomic_write_json(path, value, config.writable_roots, artifact_kind=kind, crash_after=crash_after)


def _cursor(config: EgressContractConfig, source: Mapping[str, Any] | None) -> dict[str, Any]:
    cursor = {
        "schema_version": CURSOR_SCHEMA_VERSION,
        "config_hash": config.config_hash,
        "last_source_id": None if source is None else source["source_id"],
    }
    cursor["cursor_hash"] = stable_hash(cursor)
    return cursor


def _load_all_journals(config: EgressContractConfig) -> list[dict[str, Any]]:
    journals: list[dict[str, Any]] = []
    for path in sorted(config.journal_dir.glob("*.json")):
        journal = _read_json(path, "journal")
        _validate_replay_journal(journal, str(journal.get("source_id")))
        if path.name != f"{str(journal['source_id'])[7:]}.json":
            raise EgressContractError("journal_source_path_invalid")
        journals.append(journal)
    return journals


def _recover_prepared_run(
    config: EgressContractConfig,
    journals: list[dict[str, Any]],
    existing_runs: list[Path],
) -> tuple[dict[str, Any] | None, bool]:
    if not config.cursor_path.exists():
        if existing_runs:
            raise EgressContractError("run_without_cursor")
        return None, False
    cursor = _read_json(config.cursor_path, "cursor")
    _validate_cursor(cursor, config)
    if not journals:
        raise EgressContractError("cursor_without_replay_journal")
    cursor_source_id = cursor.get("last_source_id")
    cursor_journal = next((journal for journal in journals if journal["source_id"] == cursor_source_id), None)
    if cursor_journal is None:
        raise EgressContractError("cursor_source_missing")
    prepared_entries = [entry for entry in cursor_journal["entries"] if entry["phase"] == "run_prepared"]
    cursor_entries = [entry for entry in cursor_journal["entries"] if entry["phase"] == "cursor_written"]
    if len(prepared_entries) != 1 or len(cursor_entries) > 1:
        raise EgressContractError("prepared_run_missing_or_conflicting")
    if cursor_entries and cursor_entries[0]["data"] != {"cursor_hash": cursor["cursor_hash"]}:
        raise EgressContractError("cursor_journal_binding_invalid")
    prepared = dict(prepared_entries[0]["data"]["run"])
    _validate_run(prepared)
    batch_journals = [
        journal
        for journal in journals
        if any(
            entry["phase"] == "run_prepared" and entry["data"].get("run") == prepared
            for entry in journal["entries"]
        )
    ]
    if not batch_journals:
        raise EgressContractError("prepared_run_missing_or_conflicting")
    for journal in batch_journals:
        matching_cursor = [entry for entry in journal["entries"] if entry["phase"] == "cursor_written"]
        if len(matching_cursor) > 1 or (matching_cursor and matching_cursor[0]["data"] != {"cursor_hash": cursor["cursor_hash"]}):
            raise EgressContractError("cursor_journal_binding_invalid")
        if not matching_cursor:
            current = _load_or_new_journal(config, str(journal["source_id"]))
            _append_journal(config, current, "cursor_written", {"cursor_hash": cursor["cursor_hash"]})
    run_path = config.run_dir / f"{prepared['run_hash'][7:]}.json"
    recovery_performed = not run_path.exists() or any(
        not any(entry["phase"] == "run_written" for entry in journal["entries"])
        for journal in batch_journals
    )
    if run_path.exists():
        if run_path.read_bytes() != canonical_json(prepared) + b"\n":
            raise EgressContractError("conflicting_replay_artifact")
    else:
        _atomic_write_json(run_path, prepared, config.writable_roots)
    for journal_value in batch_journals:
        journal = _load_or_new_journal(config, str(journal_value["source_id"]))
        _append_journal(config, journal, "run_written", {"run_hash": prepared["run_hash"]})
    return prepared, recovery_performed


def _recover_prepared_run_before_cursor(
    config: EgressContractConfig,
    journals: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> dict[str, Any] | None:
    prepared_journals = [
        journal
        for journal in journals
        if any(entry["phase"] == "run_prepared" for entry in journal["entries"])
        and not any(entry["phase"] == "cursor_written" for entry in journal["entries"])
    ]
    if not prepared_journals:
        return None
    prepared_runs = [
        dict(next(entry for entry in journal["entries"] if entry["phase"] == "run_prepared")["data"]["run"])
        for journal in prepared_journals
    ]
    prepared = prepared_runs[0]
    if any(run != prepared for run in prepared_runs[1:]):
        raise EgressContractError("prepared_run_conflict")
    source_ids = [str(source["source_id"]) for source in sources]
    prior_cursor_index = -1
    if config.cursor_path.exists():
        prior_cursor = _read_json(config.cursor_path, "cursor")
        _validate_cursor(prior_cursor, config)
        try:
            prior_cursor_index = source_ids.index(str(prior_cursor["last_source_id"]))
        except ValueError as exc:
            raise EgressContractError("stale_cursor") from exc
    try:
        final_index = max(source_ids.index(str(journal["source_id"])) for journal in prepared_journals)
    except ValueError as exc:
        raise EgressContractError("prepared_run_source_missing") from exc
    expected_ids = set(source_ids[prior_cursor_index + 1 : final_index + 1])
    if {str(journal["source_id"]) for journal in prepared_journals} != expected_ids:
        raise EgressContractError("prepared_run_batch_invalid")
    cursor = _cursor(config, sources[final_index])
    _atomic_write_json(config.cursor_path, cursor, config.writable_roots)
    for journal_value in prepared_journals:
        journal = _load_or_new_journal(config, str(journal_value["source_id"]))
        _append_journal(config, journal, "cursor_written", {"cursor_hash": cursor["cursor_hash"]})
    run_path = config.run_dir / f"{prepared['run_hash'][7:]}.json"
    _write_bound_artifact(run_path, prepared, config, "run")
    for journal_value in prepared_journals:
        journal = _load_or_new_journal(config, str(journal_value["source_id"]))
        _append_journal(config, journal, "run_written", {"run_hash": prepared["run_hash"]})
    return prepared


def _sources_after_cursor(config: EgressContractConfig, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_ids = [str(source["source_id"]) for source in sources]
    if len(source_ids) != len(set(source_ids)):
        raise EgressContractError("source_sequence_fork")
    if not config.cursor_path.exists():
        return sources
    cursor = _read_json(config.cursor_path, "cursor")
    _validate_cursor(cursor, config)
    try:
        cursor_index = source_ids.index(str(cursor["last_source_id"]))
    except ValueError as exc:
        raise EgressContractError("stale_cursor") from exc
    return sources[cursor_index + 1 :]


def _validate_cursor(value: Mapping[str, Any], config: EgressContractConfig) -> None:
    if set(value) != {"schema_version", "config_hash", "last_source_id", "cursor_hash"}:
        raise EgressContractError("invalid_cursor_schema")
    if value.get("schema_version") != CURSOR_SCHEMA_VERSION or value.get("config_hash") != config.config_hash:
        raise EgressContractError("cursor_binding_invalid")
    source_id = value.get("last_source_id")
    if source_id is not None:
        _hash_value(source_id, "last_source_id")
    if value.get("cursor_hash") != stable_hash({key: item for key, item in value.items() if key != "cursor_hash"}):
        raise EgressContractError("cursor_hash_invalid")


def _validate_replay_journal(value: Mapping[str, Any], source_id: str) -> None:
    if set(value) != {"schema_version", "source_id", "entries", "journal_hash"}:
        raise EgressContractError("invalid_journal_schema")
    if value.get("schema_version") != JOURNAL_SCHEMA_VERSION or value.get("source_id") != source_id:
        raise EgressContractError("journal_source_binding_invalid")
    _hash_value(source_id, "source_id")
    entries = value.get("entries")
    if not isinstance(entries, list):
        raise EgressContractError("journal_entries_invalid")
    phases: list[str] = []
    for ordinal, entry in enumerate(entries):
        if not isinstance(entry, Mapping) or set(entry) != {"ordinal", "phase", "data"} or entry.get("ordinal") != ordinal:
            raise EgressContractError("journal_ordinal_invalid")
        phase = entry.get("phase")
        data = entry.get("data")
        if phase not in _PHASES or not isinstance(data, Mapping):
            raise EgressContractError("invalid_journal_phase")
        phases.append(str(phase))
        if str(phase).endswith("_prepared"):
            _validate_prepared_journal_data(str(phase), data)
    _validate_replay_phase_graph(phases)
    if value.get("journal_hash") != stable_hash({key: item for key, item in value.items() if key != "journal_hash"}):
        raise EgressContractError("journal_hash_invalid")


def _validate_replay_phase_graph(phases: list[str]) -> None:
    index = 0
    for expected in ("validated_source", "intent_prepared", "intent_written"):
        if index == len(phases):
            return
        if phases[index] != expected:
            raise EgressContractError("journal_phase_graph_invalid")
        index += 1
    while index < len(phases) and phases[index] == "projection_prepared":
        for expected in (
            "projection_prepared",
            "projection_written",
            "capability_result_prepared",
            "capability_result_written",
        ):
            if index == len(phases):
                return
            if phases[index] != expected:
                raise EgressContractError("journal_phase_graph_invalid")
            index += 1
    for expected in ("run_prepared", "cursor_written", "run_written"):
        if index == len(phases):
            return
        if phases[index] != expected:
            raise EgressContractError("journal_phase_graph_invalid")
        index += 1
    if index != len(phases):
        raise EgressContractError("journal_phase_graph_invalid")


def _validate_prepared_journal_data(phase: str, data: Mapping[str, Any]) -> None:
    kind = {
        "intent_prepared": "intent",
        "projection_prepared": "projection",
        "capability_result_prepared": "result",
        "run_prepared": "run",
    }.get(phase)
    if kind is None or set(data) != {kind, "byte_sha256"} or not isinstance(data.get(kind), Mapping):
        raise EgressContractError("prepared_artifact_invalid")
    artifact = dict(data[kind])
    expected = "sha256:" + hashlib.sha256(canonical_json(artifact) + b"\n").hexdigest()
    if data.get("byte_sha256") != expected:
        raise EgressContractError("prepared_artifact_bytes_invalid")
    if kind == "intent":
        _validate_intent(artifact)
    elif kind == "projection":
        if artifact.get("projection_hash") != stable_hash({key: item for key, item in artifact.items() if key != "projection_hash"}):
            raise EgressContractError("projection_hash_invalid")
    elif kind == "result":
        _validate_result(artifact)
    else:
        _validate_run(artifact)


def _ensure_output_dirs(config: EgressContractConfig) -> None:
    for root in config.writable_roots:
        root.mkdir(parents=True, exist_ok=True)
        _reject_symlink_components(root)
        _require_safe_directory(root, "writable_root")
    _reserve_budget(config)


def _reserve_budget(config: EgressContractConfig) -> None:
    roots = set(config.writable_roots)
    file_count = 0
    total = 0
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            _reject_symlink_components(path)
            if path.is_file():
                file_count += 1
                total += path.stat().st_size
    if file_count > config.max_artifact_files or total > config.max_total_bytes:
        raise EgressContractError("artifact_budget_exceeded")
    if min(shutil.disk_usage(root).free for root in roots) < config.min_artifact_free_bytes:
        raise EgressContractError("artifact_free_space_exceeded")


def _atomic_write_json(
    path: Path,
    value: Mapping[str, Any],
    writable_roots: tuple[Path, ...],
    *,
    artifact_kind: str | None = None,
    crash_after: str | None = None,
) -> None:
    if not any(path == root or path.is_relative_to(root) for root in writable_roots):
        raise EgressContractError("write_outside_root")
    _reject_symlink_components(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_json(value) + b"\n"
    tmp = path.with_name(f".{path.name}.tmp")
    with tmp.open("wb") as handle:
        handle.write(data)
        handle.flush()
        _inject_crash(crash_after, artifact_kind, "file_fsync")
        os.fsync(handle.fileno())
    _inject_crash(crash_after, artifact_kind, "before_replace")
    _inject_crash(crash_after, artifact_kind, "replace")
    os.replace(tmp, path)
    _inject_crash(crash_after, artifact_kind, "after_replace")
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        _inject_crash(crash_after, artifact_kind, "directory_fsync")
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _inject_crash(crash_after: str | None, artifact_kind: str | None, stage: str) -> None:
    if artifact_kind is not None and crash_after == f"{artifact_kind}:{stage}":
        raise RuntimeError(f"injected_crash:{artifact_kind}:{stage}")


def _read_json(path: Path, kind: str) -> dict[str, Any]:
    _reject_symlink_components(path)
    _regular_file_stat(path, kind)
    if path.stat().st_size > 16_777_216:
        raise EgressContractError(f"{kind}_too_large")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EgressContractError(f"{kind}_object_required")
    return value


def _literal_path(value: Any, label: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise EgressContractError(f"invalid_{label}")
    text = str(value)
    if text.startswith("~") or "$" in text:
        raise EgressContractError("invalid_local_path")
    path = Path(text)
    if any(part in {"..", "."} for part in path.parts):
        raise EgressContractError("invalid_local_path")
    return path


def _absolute(path: Path) -> Path:
    if not path.is_absolute():
        raise EgressContractError("invalid_local_path")
    return path


def _resolve(base: Path, value: Any) -> Path:
    path = _literal_path(value, "path")
    return path if path.is_absolute() else (base / path).resolve()


def _reject_symlink_components(path: Path) -> None:
    current = Path(path.anchor) if path.is_absolute() else Path()
    for part in path.parts[1:] if path.is_absolute() else path.parts:
        current = current / part
        if current.is_symlink():
            raise EgressContractError("symlink_path_forbidden")


def _regular_file_stat(path: Path, kind: str) -> os.stat_result:
    try:
        info = path.stat()
    except OSError as exc:
        raise EgressContractError(f"{kind}_missing") from exc
    if not stat.S_ISREG(info.st_mode):
        raise EgressContractError(f"{kind}_not_regular")
    if info.st_nlink != 1:
        raise EgressContractError(f"{kind}_has_multiple_links")
    return info


def _require_safe_directory(path: Path, label: str) -> None:
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode):
        raise EgressContractError(f"{label}_not_directory")
    if info.st_uid != os.getuid():
        raise EgressContractError("wrong_owner")
    if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise EgressContractError("unsafe_directory_permissions")


def _distinct_roots(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    roots = tuple(dict.fromkeys(path if path.suffix == "" and not path.name.endswith(".json") else path.parent for path in paths))
    for index, left in enumerate(roots):
        for right in roots[index + 1 :]:
            if _overlaps(left, right):
                raise EgressContractError("writable_roots_overlap")
    return roots


def _overlaps(left: Path, right: Path) -> bool:
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _require_distinct_output_paths(*paths: Path) -> None:
    if len(set(paths)) != len(paths):
        raise EgressContractError("output_paths_overlap")


def _sequence(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise EgressContractError(f"{label}_required")
    return value


def _bounded_int(raw: Mapping[str, Any], key: str) -> int:
    value = raw.get(key)
    if type(value) is not int or value <= 0 or value > 10_000_000:
        raise EgressContractError("invalid_integer_budget")
    return value


def _safe_label(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _LABEL_RE.fullmatch(value):
        raise EgressContractError(f"invalid_{label}")
    return value


def _field_forbidden(value: str) -> bool:
    lowered = value.lower()
    return any(word in lowered for word in _FORBIDDEN_FIELD_WORDS)


def _reject_unsafe_values(value: Any) -> None:
    if isinstance(value, Mapping):
        for item in value.values():
            _reject_unsafe_values(item)
    elif isinstance(value, list):
        for item in value:
            _reject_unsafe_values(item)
    elif isinstance(value, str) and _UNSAFE_VALUE_RE.search(value):
        raise EgressContractError("forbidden_configuration_value")


def _hash_value(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise EgressContractError(f"invalid_{label}")
    return value


def _parse_utc_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not _UTC_TIMESTAMP_RE.fullmatch(value):
        raise EgressContractError("invalid_source_timestamp")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise EgressContractError("invalid_source_timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise EgressContractError("invalid_source_timestamp")
    return parsed.astimezone(UTC)


def _canonical_timestamp(value: Any) -> str:
    return _parse_utc_timestamp(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _exact_counter_map(value: Any, keys: tuple[str, ...], *, exact_zero: bool) -> bool:
    return isinstance(value, Mapping) and set(value) == set(keys) and all(type(value[key]) is int and (value[key] == 0 if exact_zero else value[key] >= 0) for key in keys)


def _expected_source_artifacts(
    config: EgressContractConfig,
    source: Mapping[str, Any],
    profile: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    intent = build_egress_intent(config, source["envelope"], source["receipt"])
    projections: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for channel in profile["channels"][: config.max_profiles_per_source]:
        projection = project_shadow_provider(intent, channel)
        if len(canonical_json(projection)) > config.max_projection_bytes:
            raise EgressContractError("projection_size_exceeded")
        projections.append(projection)
        results.append(evaluate_shadow_capability(projection, channel))
    binding = {
        "source_id": source["source_id"],
        "source_occurred_at": _canonical_timestamp(source["envelope"]["source_event"]["occurred_at"]),
        "intent_hash": intent["intent_hash"],
        "projection_hashes": [projection["projection_hash"] for projection in projections],
        "result_hashes": [result["result_hash"] for result in results],
    }
    return intent, projections, results, binding


def _build_run(
    config: EgressContractConfig,
    *,
    profile_hash: str,
    source_bindings: list[dict[str, Any]],
    counters: Mapping[str, Any],
) -> dict[str, Any]:
    if not source_bindings:
        raise EgressContractError("empty_run_source_batch")
    latest_source_timestamp = max(
        _parse_utc_timestamp(binding.get("source_occurred_at"))
        for binding in source_bindings
    )
    generated_at = latest_source_timestamp.isoformat(timespec="microseconds").replace("+00:00", "Z")
    run: dict[str, Any] = {
        "schema_version": RUN_SCHEMA_VERSION,
        "lab_id": config.lab_id,
        "config_hash": config.config_hash,
        "profile_hash": profile_hash,
        "source_batch_hash": stable_hash({"source_artifacts": source_bindings}),
        "processed_source_count": len(source_bindings),
        "result_count": sum(len(binding["result_hashes"]) for binding in source_bindings),
        "replayed_source_count": 0,
        "forbidden_counters": zero_forbidden_counters(),
        "allowed_counters": dict(counters),
        "generated_at": generated_at,
    }
    run["run_hash"] = stable_hash(run)
    _validate_run(run)
    return run


def _validate_expected_artifact_graph(
    config: EgressContractConfig,
    profile: Mapping[str, Any],
    sources: list[dict[str, Any]],
    journals: list[dict[str, Any]],
) -> None:
    source_ids = [str(source["source_id"]) for source in sources]
    source_by_id = {str(source["source_id"]): source for source in sources}
    if len(source_by_id) != len(sources):
        raise EgressContractError("source_sequence_fork")
    journal_ids = [str(journal["source_id"]) for journal in journals]
    if any(source_id not in source_by_id for source_id in journal_ids):
        raise EgressContractError("journal_source_dependency_drift")
    if journal_ids:
        positions = sorted(source_ids.index(source_id) for source_id in journal_ids)
        if positions != list(range(positions[-1] + 1)):
            raise EgressContractError("journal_source_sequence_gap")

    expected_by_source: dict[str, tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]] = {}
    run_groups: dict[str, dict[str, Any]] = {}
    for journal in journals:
        source_id = str(journal["source_id"])
        expected = _expected_source_artifacts(config, source_by_id[source_id], profile)
        expected_by_source[source_id] = expected
        intent, projections, results, _binding = expected
        validated_entries = [entry for entry in journal["entries"] if entry["phase"] == "validated_source"]
        expected_source_binding = {"source_id": source_id, "profile_hash": stable_hash(profile)}
        if validated_entries and validated_entries[0]["data"] != expected_source_binding:
            raise EgressContractError("validated_source_binding_invalid")
        _require_expected_prepared_values(journal, "intent_prepared", "intent", [intent])
        _require_expected_prepared_values(journal, "projection_prepared", "projection", projections)
        _require_expected_prepared_values(journal, "capability_result_prepared", "result", results)
        run_entries = [entry for entry in journal["entries"] if entry["phase"] == "run_prepared"]
        if not run_entries:
            continue
        if len([entry for entry in journal["entries"] if entry["phase"] == "capability_result_written"]) != len(results):
            raise EgressContractError("run_prepared_before_expected_results")
        run = dict(run_entries[0]["data"]["run"])
        group = run_groups.setdefault(run["run_hash"], {"run": run, "journals": []})
        if group["run"] != run:
            raise EgressContractError("prepared_run_conflict")
        group["journals"].append(journal)

    profile_hash = stable_hash(profile)
    cumulative_projection_count = 0
    cumulative_result_count = 0
    cumulative_failure_count = 0
    cumulative_journal_count = 0
    consumed_sources = 0
    ordered_groups = sorted(
        run_groups.values(),
        key=lambda group: max(source_ids.index(str(journal["source_id"])) for journal in group["journals"]),
    )
    expected_cursor_hashes: set[str] = set()
    for group in ordered_groups:
        group_journals = sorted(group["journals"], key=lambda journal: source_ids.index(str(journal["source_id"])))
        group_positions = [source_ids.index(str(journal["source_id"])) for journal in group_journals]
        if group_positions != list(range(consumed_sources, consumed_sources + len(group_journals))):
            raise EgressContractError("prepared_run_batch_invalid")
        bindings = [expected_by_source[str(journal["source_id"])][3] for journal in group_journals]
        group_results = [
            result
            for journal in group_journals
            for result in expected_by_source[str(journal["source_id"])][2]
        ]
        cumulative_projection_count += sum(len(binding["projection_hashes"]) for binding in bindings)
        cumulative_result_count += len(group_results)
        cumulative_failure_count += sum(not result["compatible"] for result in group_results)
        for journal in group_journals:
            phases = {str(entry["phase"]) for entry in journal["entries"]}
            cumulative_journal_count += len(journal["entries"]) + sum(
                phase not in phases for phase in ("cursor_written", "run_written")
            )
        counters = zero_allowed_counters()
        counters.update(
            {
                "capability_manifest_write_count": cumulative_result_count,
                "compatibility_failure_count": cumulative_failure_count,
                "intent_projection_count": cumulative_projection_count,
                "replay_journal_entry_count": cumulative_journal_count,
                "shadow_provider_validation_count": cumulative_result_count,
            }
        )
        expected_run = _build_run(
            config,
            profile_hash=profile_hash,
            source_bindings=bindings,
            counters=counters,
        )
        if group["run"] != expected_run:
            raise EgressContractError("expected_run_binding_invalid")
        final_source = source_by_id[str(group_journals[-1]["source_id"])]
        expected_cursor = _cursor(config, final_source)
        expected_cursor_hashes.add(expected_cursor["cursor_hash"])
        for journal in group_journals:
            cursor_entries = [entry for entry in journal["entries"] if entry["phase"] == "cursor_written"]
            if cursor_entries and cursor_entries[0]["data"] != {"cursor_hash": expected_cursor["cursor_hash"]}:
                raise EgressContractError("expected_cursor_binding_invalid")
        consumed_sources += len(group_journals)

    if config.cursor_path.exists():
        cursor = _read_json(config.cursor_path, "cursor")
        _validate_cursor(cursor, config)
        if config.cursor_path.read_bytes() != canonical_json(cursor) + b"\n":
            raise EgressContractError("conflicting_replay_artifact")
        if cursor["cursor_hash"] not in expected_cursor_hashes:
            raise EgressContractError("expected_cursor_binding_invalid")


def _require_expected_prepared_values(
    journal: Mapping[str, Any],
    phase: str,
    kind: str,
    expected_values: list[dict[str, Any]],
) -> None:
    entries = [entry for entry in journal["entries"] if entry["phase"] == phase]
    if len(entries) > len(expected_values):
        raise EgressContractError("unexpected_prepared_artifact")
    for entry, expected in zip(entries, expected_values, strict=False):
        if entry["data"].get(kind) != expected:
            raise EgressContractError("expected_prepared_artifact_mismatch")
        expected_hash = "sha256:" + hashlib.sha256(canonical_json(expected) + b"\n").hexdigest()
        if entry["data"].get("byte_sha256") != expected_hash:
            raise EgressContractError("expected_prepared_bytes_mismatch")


def _validate_existing_artifacts(config: EgressContractConfig, journals: list[dict[str, Any]]) -> None:
    expected_paths: dict[str, set[Path]] = {
        "intent": set(),
        "projection": set(),
        "result": set(),
        "run": set(),
    }
    for journal in journals:
        intent_entries = [entry for entry in journal["entries"] if entry["phase"] == "intent_prepared"]
        projection_entries = [entry for entry in journal["entries"] if entry["phase"] == "projection_prepared"]
        result_entries = [entry for entry in journal["entries"] if entry["phase"] == "capability_result_prepared"]
        if (
            len(intent_entries) > 1
            or len(result_entries) > len(projection_entries)
            or len(projection_entries) - len(result_entries) > 1
        ):
            raise EgressContractError("prepared_artifact_binding_invalid")
        intent = dict(intent_entries[0]["data"]["intent"]) if intent_entries else None
        projections = [dict(entry["data"]["projection"]) for entry in projection_entries]
        results = [dict(entry["data"]["result"]) for entry in result_entries]
        if intent is not None:
            for projection in projections:
                if projection.get("intent_id") != intent["intent_id"] or projection.get("intent_hash") != intent["intent_hash"]:
                    raise EgressContractError("prepared_projection_binding_invalid")
        for projection, result in zip(projections, results, strict=False):
            if result.get("projection_id") != projection["projection_id"] or result.get("projection_hash") != projection["projection_hash"]:
                raise EgressContractError("prepared_result_binding_invalid")
        _validate_prepared_published_pairs(
            journal,
            "intent_prepared",
            "intent_written",
            "intent",
            "intent_id",
            "intent_hash",
            config.intent_dir,
            expected_paths["intent"],
        )
        _validate_prepared_published_pairs(
            journal,
            "projection_prepared",
            "projection_written",
            "projection",
            "projection_id",
            "projection_hash",
            config.projection_dir,
            expected_paths["projection"],
        )
        _validate_prepared_published_pairs(
            journal,
            "capability_result_prepared",
            "capability_result_written",
            "result",
            "result_id",
            "result_hash",
            config.result_dir,
            expected_paths["result"],
        )
        _validate_prepared_published_pairs(
            journal,
            "run_prepared",
            "run_written",
            "run",
            "run_hash",
            "run_hash",
            config.run_dir,
            expected_paths["run"],
        )
    actual_paths = {
        "intent": set(config.intent_dir.glob("*.json")),
        "projection": set(config.projection_dir.glob("*.json")),
        "result": set(config.result_dir.glob("*.json")),
        "run": set(config.run_dir.glob("*.json")),
    }
    if any(actual_paths[kind] - expected_paths[kind] for kind in expected_paths):
        raise EgressContractError("conflicting_replay_artifact")


def _validate_prepared_published_pairs(
    journal: Mapping[str, Any],
    prepared_phase: str,
    written_phase: str,
    kind: str,
    id_field: str,
    hash_field: str,
    directory: Path,
    expected_paths: set[Path],
) -> None:
    prepared_entries = [entry for entry in journal["entries"] if entry["phase"] == prepared_phase]
    written_entries = [entry for entry in journal["entries"] if entry["phase"] == written_phase]
    if len(written_entries) > len(prepared_entries):
        raise EgressContractError("prepared_artifact_binding_invalid")
    for index, prepared_entry in enumerate(prepared_entries):
        artifact = dict(prepared_entry["data"][kind])
        artifact_path = directory / f"{str(artifact[id_field])[7:]}.json"
        expected_paths.add(artifact_path)
        expected_bytes = canonical_json(artifact) + b"\n"
        if artifact_path.exists() and artifact_path.read_bytes() != expected_bytes:
            raise EgressContractError("conflicting_replay_artifact")
        if index < len(written_entries):
            if written_entries[index]["data"] != {hash_field: artifact[hash_field]}:
                raise EgressContractError("written_artifact_binding_invalid")
            if not artifact_path.exists():
                raise EgressContractError("written_artifact_missing")


def _artifact_allowed_counters(
    config: EgressContractConfig,
    journals: list[dict[str, Any]],
    *,
    anticipated_terminal_source_ids: set[str] | None = None,
) -> dict[str, int]:
    projections = [_read_json(path, "projection") for path in sorted(config.projection_dir.glob("*.json"))]
    results = [_read_json(path, "result") for path in sorted(config.result_dir.glob("*.json"))]
    for projection in projections:
        if projection.get("projection_hash") != stable_hash(
            {key: item for key, item in projection.items() if key != "projection_hash"}
        ):
            raise EgressContractError("projection_hash_invalid")
    for result in results:
        _validate_result(result)
    journal_count = sum(len(journal["entries"]) for journal in journals)
    if anticipated_terminal_source_ids:
        for journal in journals:
            if journal["source_id"] not in anticipated_terminal_source_ids:
                continue
            phases = {str(entry["phase"]) for entry in journal["entries"]}
            journal_count += sum(phase not in phases for phase in ("run_prepared", "cursor_written", "run_written"))
    counters = zero_allowed_counters()
    counters.update(
        {
            "capability_manifest_write_count": len(results),
            "compatibility_failure_count": sum(not bool(result["compatible"]) for result in results),
            "intent_projection_count": len(projections),
            "replay_journal_entry_count": journal_count,
            "shadow_provider_validation_count": len(results),
        }
    )
    return counters


def _validate_run_counter_bindings(
    config: EgressContractConfig,
    run: Mapping[str, Any],
    journals: list[dict[str, Any]],
) -> None:
    if run.get("allowed_counters") != _artifact_allowed_counters(config, journals):
        raise EgressContractError("allowed_counter_artifact_mismatch")


class _Lease:
    def __init__(self, config: EgressContractConfig) -> None:
        self.config = config
        self.handle: Any | None = None

    def __enter__(self) -> None:
        self.config.lease_path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.config.lease_path.open("w", encoding="utf-8")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise EgressContractError("lease_conflict") from exc

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
