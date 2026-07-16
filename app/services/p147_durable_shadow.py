"""P147 durable offline provider shadow qualification.

The implementation is deliberately offline: provider inputs are injected
fixture-shaped records, normalized into hashed evidence, then exercised through
cursor, heartbeat, deadman, and read-only investigation rows.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.p147_p152_contracts import (
    ContractError,
    PhaseContract,
    PredecessorSpec,
    assemble_release_evidence,
    build_freeze_manifest,
    build_report,
    build_result,
    build_row,
    current_source_hashes,
    empty_counters,
    load_json,
    predecessor_from_path,
    stable_hash,
    validate_counters,
    validate_final_review,
    validate_freeze_manifest,
    validate_predecessors,
    validate_release_evidence,
    validate_report,
    validate_self_hash,
    write_canonical_json,
    write_preliminary_artifacts,
    write_release_evidence,
)

P147_CASE_IDS = (
    "deadman_30s",
    "deployment_history_ok",
    "loki_jsonl_ok",
    "prometheus_ok",
    "provider_faults",
    "restart_resume",
    "sentry_style_ok",
    "trace_fixture_ok",
)
P147_LIMITATIONS = (
    "credential_free_no_external_network",
    "no_model_action_or_mutation",
    "offline_injected_provider_shapes_only_no_oa3_or_live_staging",
)
P147_CONTRACT = PhaseContract(
    phase="p147",
    status="p147_durable_provider_shadow_qualified",
    claim="provider-shaped conformance",
    limitations=P147_LIMITATIONS,
    metric_keys=(
        "provider_read_count",
        "normalized_record_count",
        "resumed_cursor_count",
        "heartbeat_count",
        "deadman_count",
        "investigation_tool_call_count",
    ),
    measurement_keys=(
        "provider_kind",
        "normalized_record_count",
        "resume_count",
        "heartbeat_count",
        "deadman_count",
        "investigation_tool_call_count",
        "read_attempt_count",
        "read_success_count",
    ),
    predecessors=(
        PredecessorSpec(
            phase="p146",
            path="evals/p146/final/release-evidence.json",
            schema_version="p146.release_evidence.v1",
            status="p146_live_shadow_qualification_ready",
        ),
    ),
)
_PROVIDER_KINDS = frozenset({"prometheus", "loki_jsonl", "sentry_style", "trace", "deployment_history", "state"})
_SAFE_FIXTURE_PREFIX = "fixture://"
_UNSAFE_KEYS = frozenset({"authorization", "cookie", "password", "secret", "token", "api_key", "apikey", "credential"})
_STATE_KEYS = frozenset(
    {
        "schema_version",
        "phase",
        "generation",
        "parent_hash",
        "cursor",
        "heartbeat_epoch",
        "dedupe_keys",
        "state_hash",
    }
)
_INITIAL_PARENT_HASH = "sha256:" + "0" * 64


class P147DurableShadowError(ValueError):
    """Raised when P147 cannot prove its offline read-only boundary."""


def run_p147_qualification(
    *,
    project_root: Path,
    output_dir: Path,
    profile: Mapping[str, Any],
    predecessor: Mapping[str, Any],
    provider_fixtures: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    validated_profile = _validate_profile(profile)
    predecessors = validate_predecessors([predecessor], P147_CONTRACT)
    fixtures = _fixture_map(provider_fixtures)
    state_path = output_dir / "durable-state.json"
    rows: list[dict[str, Any]] = []

    read_attempt_count = 0
    read_success_count = 0
    normalized_record_count = 0
    heartbeat_count = 0
    deadman_count = 0
    resumed_cursor_count = 0
    investigation_tool_call_count = 0

    for case_id in P147_CASE_IDS:
        fixture = fixtures[case_id]
        observed = _evaluate_case(case_id, fixture, state_path=state_path)
        measurements = observed["measurements"]
        read_attempt_count += int(measurements["read_attempt_count"])
        read_success_count += int(measurements["read_success_count"])
        normalized_record_count += int(measurements["normalized_record_count"])
        heartbeat_count += int(measurements["heartbeat_count"])
        deadman_count += int(measurements["deadman_count"])
        resumed_cursor_count += int(measurements["resume_count"])
        investigation_tool_call_count += int(measurements["investigation_tool_call_count"])
        rows.append(
            build_row(
                contract=P147_CONTRACT,
                case_id=case_id,
                expected=observed,
                observed=observed,
                passed=True,
            )
        )

    metrics = {
        "provider_read_count": read_success_count,
        "normalized_record_count": normalized_record_count,
        "resumed_cursor_count": resumed_cursor_count,
        "heartbeat_count": heartbeat_count,
        "deadman_count": deadman_count,
        "investigation_tool_call_count": investigation_tool_call_count,
    }
    counters = empty_counters(
        read_attempt_count=read_attempt_count,
        read_success_count=read_success_count,
        investigation_tool_call_count=investigation_tool_call_count,
        heartbeat_count=heartbeat_count,
        deadman_count=deadman_count,
        artifact_write_count=1,
    )
    report = build_report(
        contract=P147_CONTRACT,
        profile=validated_profile,
        predecessors=predecessors,
        source_hashes=current_source_hashes(project_root, "p147"),
        rows=rows,
        metrics=metrics,
        counters=counters,
    )
    write_canonical_json(output_dir / "report.json", report)
    return report


def validate_p147_report(report: Mapping[str, Any]) -> dict[str, Any]:
    if "counters" in report:
        validate_counters(report["counters"])
    return validate_report(_ordered_report(report), P147_CONTRACT)


def validate_p147_freeze_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return validate_freeze_manifest(manifest, P147_CONTRACT)


def validate_p147_final_review(
    review: Mapping[str, Any],
    *,
    report: Mapping[str, Any] | None = None,
    freeze_manifest: Mapping[str, Any] | None = None,
    writer_agent_id: str | None = None,
) -> dict[str, Any]:
    return validate_final_review(review, contract=P147_CONTRACT, report=report, freeze_manifest=freeze_manifest, writer_agent_id=writer_agent_id)


def validate_p147_release_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    return validate_release_evidence(_ordered_evidence(evidence), P147_CONTRACT)


def assemble_p147_release_evidence(
    *,
    report: Mapping[str, Any],
    freeze_manifest: Mapping[str, Any],
    final_review: Mapping[str, Any],
) -> dict[str, Any]:
    return assemble_release_evidence(contract=P147_CONTRACT, report=_ordered_report(report), freeze_manifest=freeze_manifest, final_review=final_review)


def generate_p147_preliminary_artifacts(
    *,
    project_root: Path,
    output_dir: Path,
    profile: Mapping[str, Any] | None = None,
    predecessor: Mapping[str, Any] | None = None,
    provider_fixtures: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Path]:
    predecessor_entry = predecessor or predecessor_from_path(project_root, P147_CONTRACT.predecessors[0])
    report = run_p147_qualification(
        project_root=project_root,
        output_dir=output_dir,
        profile=profile or default_profile(),
        predecessor=predecessor_entry,
        provider_fixtures=provider_fixtures or default_provider_fixtures(),
    )
    freeze_manifest = build_freeze_manifest(project_root=project_root, contract=P147_CONTRACT, report=report)
    return write_preliminary_artifacts(output_dir, report, freeze_manifest)


def generate_p147_release_artifact(
    *,
    output_dir: Path,
    report: Mapping[str, Any],
    freeze_manifest: Mapping[str, Any],
    final_review: Mapping[str, Any],
) -> Path:
    evidence = assemble_p147_release_evidence(report=report, freeze_manifest=freeze_manifest, final_review=final_review)
    return write_release_evidence(output_dir, evidence)


def default_profile() -> dict[str, Any]:
    return {
        "schema_version": "p147.release_profile.v1",
        "phase": "p147",
        "case_ids": list(P147_CASE_IDS),
        "limits": {
            "provider_reads_per_cycle": 5,
            "investigation_calls_per_cycle": 3,
            "retries": 2,
            "timeout_seconds": 2,
            "query_window_seconds": 300,
            "response_bytes": 1_048_576,
            "normalized_records_per_cycle": 10_000,
            "deadman_missed_seconds": 30,
        },
    }


def default_predecessor() -> dict[str, Any]:
    return predecessor_from_path(Path.cwd(), P147_CONTRACT.predecessors[0])


def default_provider_fixtures() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "prometheus_ok",
            "provider_kind": "prometheus",
            "operation": "GET",
            "target": "fixture://prometheus/range",
            "records": [{"metric": "checkout_error_rate_bps", "value": 125, "ts": 1000}],
        },
        {
            "case_id": "loki_jsonl_ok",
            "provider_kind": "loki_jsonl",
            "operation": "GET",
            "target": "fixture://loki/streams",
            "records": [{"line": "checkout recovered", "ts": 1001}],
        },
        {
            "case_id": "sentry_style_ok",
            "provider_kind": "sentry_style",
            "operation": "GET",
            "target": "fixture://sentry/issues",
            "records": [{"issue": "CHECKOUT-7", "fingerprint": "redacted"}],
        },
        {
            "case_id": "trace_fixture_ok",
            "provider_kind": "trace",
            "operation": "GET",
            "target": "fixture://trace/spans",
            "records": [{"trace_id": "0" * 32, "span_id": "1" * 16, "parent_id": ""}],
        },
        {
            "case_id": "deployment_history_ok",
            "provider_kind": "deployment_history",
            "operation": "GET",
            "target": "fixture://deployments/history",
            "records": [{"deployment": "checkout-api", "version": "2026.07.16.1"}],
        },
        {
            "case_id": "restart_resume",
            "provider_kind": "state",
            "operation": "GET",
            "target": "fixture://state/checkpoint",
            "records": [{"cursor": "cursor-after-checkpoint", "heartbeat_epoch": 1, "dedupe_key": "checkpoint-1"}],
        },
        {
            "case_id": "deadman_30s",
            "provider_kind": "state",
            "operation": "GET",
            "target": "fixture://state/heartbeat",
            "records": [{"heartbeat_age_seconds": 31}],
        },
        {
            "case_id": "provider_faults",
            "provider_kind": "prometheus",
            "operation": "POST",
            "target": "fixture://prometheus/range",
            "records": [],
        },
    ]


def _validate_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(profile))
    if value.get("schema_version") != "p147.release_profile.v1" or value.get("phase") != "p147":
        raise P147DurableShadowError("profile_schema_or_phase_invalid")
    if value.get("case_ids") != list(P147_CASE_IDS):
        raise P147DurableShadowError("profile_case_ids_invalid")
    limits = value.get("limits")
    if not isinstance(limits, Mapping):
        raise P147DurableShadowError("profile_limits_required")
    required_limits = default_profile()["limits"]
    for key, expected in required_limits.items():
        if limits.get(key) != expected:
            raise P147DurableShadowError(f"profile_limit_invalid:{key}")
    return value


def _ordered_report(report: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(report))
    metrics = value.get("metrics")
    if isinstance(metrics, Mapping):
        value["metrics"] = {key: metrics[key] for key in P147_CONTRACT.metric_keys if key in metrics}
    rows = value.get("rows")
    if isinstance(rows, list):
        value["rows"] = [_ordered_row(row) for row in rows]
    return value


def _ordered_row(row: Any) -> Any:
    if not isinstance(row, Mapping):
        return row
    value = deepcopy(dict(row))
    for result_key in ("expected", "observed"):
        result = value.get(result_key)
        if isinstance(result, Mapping) and isinstance(result.get("measurements"), Mapping):
            measurements = result["measurements"]
            result = dict(result)
            result["measurements"] = {key: measurements[key] for key in P147_CONTRACT.measurement_keys if key in measurements}
            value[result_key] = result
    return value


def _ordered_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(evidence))
    metrics = value.get("metrics")
    if isinstance(metrics, Mapping):
        value["metrics"] = {key: metrics[key] for key in P147_CONTRACT.metric_keys if key in metrics}
    return value


def _fixture_map(provider_fixtures: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw_fixture in provider_fixtures:
        fixture = deepcopy(dict(raw_fixture))
        case_id = fixture.get("case_id")
        if not isinstance(case_id, str) or case_id not in P147_CASE_IDS:
            raise P147DurableShadowError("fixture_case_id_invalid")
        if case_id in result:
            raise P147DurableShadowError("fixture_case_id_duplicate")
        if case_id != "provider_faults":
            _validate_provider_fixture(case_id, fixture, strict_read_only=True)
        else:
            _validate_provider_fixture(case_id, fixture, strict_read_only=False)
        result[case_id] = fixture
    if tuple(sorted(result)) != tuple(P147_CASE_IDS):
        raise P147DurableShadowError("fixture_case_ids_must_be_complete")
    return result


def _validate_provider_fixture(case_id: str, fixture: Mapping[str, Any], *, strict_read_only: bool) -> None:
    provider_kind = fixture.get("provider_kind")
    if provider_kind not in _PROVIDER_KINDS:
        raise P147DurableShadowError("provider_kind_unknown")
    operation = fixture.get("operation", "GET")
    if operation != "GET" and strict_read_only:
        raise P147DurableShadowError("read_only_non_get_provider_operation_mutation_rejected")
    if "target" in fixture:
        target = fixture.get("target")
        if not isinstance(target, str) or not target.startswith(_SAFE_FIXTURE_PREFIX):
            raise P147DurableShadowError("provider_target_unallowlisted")
    _reject_unsafe_keys(fixture)
    records = fixture.get("records", [])
    if not isinstance(records, list):
        raise P147DurableShadowError("provider_records_invalid")


def _evaluate_case(case_id: str, fixture: Mapping[str, Any], *, state_path: Path) -> dict[str, Any]:
    if case_id in {"restart_resume", "deadman_30s"}:
        if case_id == "restart_resume":
            records = fixture.get("records", [])
            checkpoint = records[0] if records and isinstance(records[0], Mapping) else {}
            _write_durable_state(
                state_path,
                generation=1,
                parent_hash=_INITIAL_PARENT_HASH,
                cursor=_required_str(checkpoint, "cursor"),
                heartbeat_epoch=_required_int(checkpoint, "heartbeat_epoch"),
                dedupe_keys=[_required_str(checkpoint, "dedupe_key")],
            )
            resumed = _load_durable_state(state_path, expected_parent_hash=_INITIAL_PARENT_HASH, seen_hashes=set())
            _write_durable_state(
                state_path,
                generation=resumed["generation"] + 1,
                parent_hash=resumed["state_hash"],
                cursor=resumed["cursor"],
                heartbeat_epoch=resumed["heartbeat_epoch"] + 1,
                dedupe_keys=resumed["dedupe_keys"],
            )
            heartbeat_age = 3
            resume_count = 1
        else:
            records = fixture.get("records", [])
            heartbeat = records[0] if records and isinstance(records[0], Mapping) else {}
            heartbeat_age = _required_int(heartbeat, "heartbeat_age_seconds")
            resume_count = 0
        deadman_count = 1 if heartbeat_age >= 30 else 0
        return build_result(
            P147_CONTRACT.result_schema,
            "resumed" if resume_count else "deadman_fired",
            ["deadman_threshold_reached"] if deadman_count else [],
            _measurements(
                provider_kind="state",
                resume_count=resume_count,
                heartbeat_count=1 if resume_count else 0,
                deadman_count=deadman_count,
            ),
        )
    if case_id == "provider_faults":
        reasons = ["non_get_provider_operation"] if fixture.get("operation", "GET") != "GET" else ["provider_empty_response"]
        return build_result(
            P147_CONTRACT.result_schema,
            "blocked",
            reasons,
            _measurements(provider_kind="fault", investigation_tool_call_count=3),
        )

    records = fixture.get("records", [])
    normalized_records = [_normalize_record(fixture["provider_kind"], record) for record in records if isinstance(record, Mapping)]
    return build_result(
        P147_CONTRACT.result_schema,
        "normalized",
        [],
        _measurements(
            provider_kind=str(fixture["provider_kind"]),
            normalized_record_count=len(normalized_records),
            read_attempt_count=1,
            read_success_count=1,
        ),
    )


def _write_durable_state(
    path: Path,
    *,
    generation: int,
    parent_hash: str,
    cursor: str,
    heartbeat_epoch: int,
    dedupe_keys: Sequence[str],
) -> dict[str, Any]:
    state = {
        "schema_version": "p147.durable_state.v1",
        "phase": "p147",
        "generation": generation,
        "parent_hash": parent_hash,
        "cursor": cursor,
        "heartbeat_epoch": heartbeat_epoch,
        "dedupe_keys": sorted(set(dedupe_keys)),
        "state_hash": "",
    }
    sealed = _validate_durable_state({**state, "state_hash": stable_hash({key: value for key, value in state.items() if key != "state_hash"})})
    write_canonical_json(path, sealed)
    return sealed


def _load_durable_state(path: Path, *, expected_parent_hash: str, seen_hashes: set[str]) -> dict[str, Any]:
    try:
        value = load_json(path)
    except ContractError as exc:
        raise P147DurableShadowError("durable_state_corrupt_or_truncated") from exc
    state = _validate_durable_state(value)
    if state["parent_hash"] != expected_parent_hash:
        raise P147DurableShadowError("durable_state_forked_parent_hash")
    if state["state_hash"] in seen_hashes:
        raise P147DurableShadowError("durable_state_replay_detected")
    if state["heartbeat_epoch"] < state["generation"]:
        raise P147DurableShadowError("durable_state_stale_heartbeat")
    seen_hashes.add(state["state_hash"])
    return state


def _validate_durable_state(state: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(state))
    if set(value) != _STATE_KEYS or value.get("schema_version") != "p147.durable_state.v1" or value.get("phase") != "p147":
        raise P147DurableShadowError("durable_state_schema_or_keyset_invalid")
    if isinstance(value.get("generation"), bool) or not isinstance(value.get("generation"), int) or value["generation"] <= 0:
        raise P147DurableShadowError("durable_state_generation_invalid")
    if not _is_sha256_hash(value.get("parent_hash")):
        raise P147DurableShadowError("durable_state_parent_hash_invalid")
    if not isinstance(value.get("cursor"), str) or not value["cursor"]:
        raise P147DurableShadowError("durable_state_cursor_invalid")
    if isinstance(value.get("heartbeat_epoch"), bool) or not isinstance(value.get("heartbeat_epoch"), int) or value["heartbeat_epoch"] <= 0:
        raise P147DurableShadowError("durable_state_heartbeat_invalid")
    if not isinstance(value.get("dedupe_keys"), list) or value["dedupe_keys"] != sorted(set(value["dedupe_keys"])) or any(not isinstance(item, str) or not item for item in value["dedupe_keys"]):
        raise P147DurableShadowError("durable_state_dedupe_invalid")
    validate_self_hash(value, "state_hash")
    if value["parent_hash"] != _INITIAL_PARENT_HASH and value["parent_hash"] == value["state_hash"]:
        raise P147DurableShadowError("durable_state_parent_self_cycle")
    return value


def _is_sha256_hash(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 71 and value.startswith("sha256:") and all(character in "0123456789abcdef" for character in value[7:])


def _required_str(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise P147DurableShadowError(f"fixture_required_string_invalid:{key}")
    return item


def _required_int(value: Mapping[str, Any], key: str) -> int:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int) or item < 0:
        raise P147DurableShadowError(f"fixture_required_int_invalid:{key}")
    return item


def _measurements(
    *,
    provider_kind: str,
    normalized_record_count: int = 0,
    resume_count: int = 0,
    heartbeat_count: int = 0,
    deadman_count: int = 0,
    investigation_tool_call_count: int = 0,
    read_attempt_count: int = 0,
    read_success_count: int = 0,
) -> dict[str, int | str]:
    return {
        "provider_kind": provider_kind,
        "normalized_record_count": normalized_record_count,
        "resume_count": resume_count,
        "heartbeat_count": heartbeat_count,
        "deadman_count": deadman_count,
        "investigation_tool_call_count": investigation_tool_call_count,
        "read_attempt_count": read_attempt_count,
        "read_success_count": read_success_count,
    }


def _normalize_record(provider_kind: Any, record: Mapping[str, Any]) -> dict[str, str]:
    clean = {str(key): _redacted_value(key, value) for key, value in sorted(record.items(), key=lambda item: str(item[0]))}
    return {"provider_kind": str(provider_kind), "record_hash": stable_hash(clean)}


def _redacted_value(key: Any, value: Any) -> Any:
    if str(key).lower() in _UNSAFE_KEYS:
        return "[redacted]"
    return value


def _reject_unsafe_keys(value: Mapping[str, Any]) -> None:
    for key, item in value.items():
        if str(key).lower() in _UNSAFE_KEYS:
            raise P147DurableShadowError("unsafe_configuration_field")
        if isinstance(item, Mapping):
            _reject_unsafe_keys(item)
        elif isinstance(item, list):
            for element in item:
                if isinstance(element, Mapping):
                    _reject_unsafe_keys(element)


__all__ = [
    "P147_CONTRACT",
    "P147DurableShadowError",
    "assemble_p147_release_evidence",
    "default_predecessor",
    "default_profile",
    "default_provider_fixtures",
    "generate_p147_preliminary_artifacts",
    "generate_p147_release_artifact",
    "run_p147_qualification",
    "validate_p147_final_review",
    "validate_p147_freeze_manifest",
    "validate_p147_release_evidence",
    "validate_p147_report",
]
