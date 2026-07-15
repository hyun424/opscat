"""Portable CLI for one bounded P146 live-shadow episode."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash

PROFILE_SCHEMA_VERSION = "p146.release_profile.v1"
RECEIPT_SCHEMA_VERSION = "p146.cli_episode_receipt.v1"
RECEIPTS_SCHEMA_VERSION = "p146.cli_episode_receipts.v1"
PREDICTION_ARTIFACT = "prediction.json"
RECEIPTS_ARTIFACT = "receipts.json"
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
PREDICTION_KEYS = (
    "schema_version",
    "case_ref_hash",
    "incident_detected",
    "diagnostic_disposition",
    "ranked_hypotheses",
    "p14_route",
    "final_shadow_route",
    "safety_overlay",
    "citations",
    "missing_providers",
    "executed_actions",
    "runtime_counters",
    "forbidden_counters",
    "prediction_hash",
)
COUNTER_GROUPS = ("runtime", "evaluator", "resources", "forbidden")
RUNTIME_COUNTER_KEYS = (
    "capability_validation_count",
    "loopback_socket_attempt_count",
    "request_commit_count",
    "request_byte_count",
    "complete_response_count",
    "response_byte_count",
    "provider_record_count",
    "normalized_evidence_count",
    "context_build_count",
    "mock_judgment_call_count",
    "unclassified_signal_count",
)
EVALUATOR_COUNTER_KEYS = (
    "listener_bind_count",
    "accepted_connection_count",
    "server_response_count",
    "server_response_byte_count",
    "visible_state_change_count",
    "truth_read_count",
    "score_operation_count",
    "artifact_write_count",
    "structural_health_call_count",
    "structural_readiness_call_count",
)
RESOURCE_COUNTER_KEYS = (
    "wall_time_ns",
    "cpu_time_ns",
    "peak_memory_kib",
    "max_response_bytes",
    "artifact_bytes",
)
FORBIDDEN_COUNTER_KEYS = (
    "credential_read_count",
    "secret_read_count",
    "environment_read_count",
    "dns_call_count",
    "non_loopback_socket_count",
    "unix_socket_count",
    "tls_handshake_count",
    "proxy_use_count",
    "redirect_follow_count",
    "external_http_count",
    "external_provider_call_count",
    "provider_sdk_call_count",
    "external_model_call_count",
    "external_message_count",
    "shell_count",
    "subprocess_action_count",
    "freeform_command_count",
    "action_intent_count",
    "action_commit_count",
    "action_execution_count",
    "remediation_count",
    "rollback_count",
    "p133_ack_count",
    "external_approval_count",
    "ticket_creation_count",
    "outside_artifact_write_count",
    "staging_mutation_count",
    "production_mutation_count",
    "live_proof_count",
    "operator_replacement_count",
    "authority_escape_count",
)
COUNTER_KEYS = {
    "runtime": RUNTIME_COUNTER_KEYS,
    "evaluator": EVALUATOR_COUNTER_KEYS,
    "resources": RESOURCE_COUNTER_KEYS,
    "forbidden": FORBIDDEN_COUNTER_KEYS,
}
LEAK_KEY_MARKERS = (
    "raw",
    "raw_bytes",
    "payload_bytes",
    "body_bytes",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
    "endpoint",
    "url",
    "host",
    "port",
)
LEAK_TEXT_MARKERS = (
    "://",
    "localhost",
    "127.0.0.1",
    "0:0:0:0:0:0:0:1",
    "::1",
    "bearer ",
)


class P146CliError(ValueError):
    """Raised when a P146 CLI episode cannot be run safely."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one portable P146 bounded live-shadow episode.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--profile", required=True, type=Path)
    run_parser.add_argument("--output", required=True, type=Path)
    run_parser.add_argument("--case", required=True, dest="case_id")
    args = parser.parse_args(argv)

    try:
        if args.command == "run":
            receipt = run_episode(profile_path=args.profile, output_dir=args.output, case_id=args.case_id)
            print(_canonical_json(receipt))
            return 0
    except Exception as exc:
        print(_canonical_json({"schema_version": RECEIPT_SCHEMA_VERSION, "status": "blocked", "error": str(exc), "error_type": type(exc).__name__}), file=sys.stderr)
        return 1
    raise P146CliError(f"unknown_command:{args.command}")


def run_episode(*, profile_path: Path, output_dir: Path, case_id: str) -> dict[str, Any]:
    profile = _read_json(profile_path)
    corpus = _profile_corpus(profile)
    corpus_hash = _corpus_hash(corpus)
    profile_hash = _profile_hash(corpus_hash)
    _validate_profile_hashes(profile, corpus_hash=corpus_hash, profile_hash=profile_hash)
    visible_case = _select_visible_case(corpus, case_id)
    case_ref_hash = stable_hash({"p146_case_ref": case_id})

    # Import lazily so the CLI can be imported while the P146 core is developed independently.
    core = importlib.import_module("app.services.p146_live_shadow")

    episode = _json_ready(core.run_live_shadow_episode(visible_case))
    _validate_episode(episode, core=core)
    prediction = _build_prediction_artifact(
        _extract_prediction(episode, visible_case=visible_case, core=core),
        aggregate_counters=_aggregate_counters(episode),
        case_ref_hash=case_ref_hash,
    )
    receipts = _build_receipts(
        case_ref_hash=case_ref_hash,
        corpus_hash=corpus_hash,
        episode=episode,
        prediction=prediction,
        profile_hash=profile_hash,
    )

    output_dir = _prepare_output_dir(output_dir)
    prediction_path = output_dir / PREDICTION_ARTIFACT
    receipts_path = output_dir / RECEIPTS_ARTIFACT
    _write_json_atomic(prediction_path, prediction)
    _write_json_atomic(receipts_path, receipts)

    authority_counters = _forbidden_counters_from_episode(episode)
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "status": "ok",
        "case_ref_hash": case_ref_hash,
        "artifact_root": output_dir.name,
        "artifacts": {
            "prediction": PREDICTION_ARTIFACT,
            "receipts": RECEIPTS_ARTIFACT,
        },
        "profile_hash": profile_hash,
        "corpus_hash": corpus_hash,
        "prediction_hash": stable_hash(prediction),
        "receipts_hash": stable_hash(receipts),
        "authority_counters": authority_counters,
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_json_object)
    if not isinstance(value, dict):
        raise P146CliError("profile_json_object_required")
    return value


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise P146CliError(f"duplicate_json_key:{key}")
        value[key] = item
    return value


def _profile_corpus(profile: Mapping[str, Any]) -> Mapping[str, Any]:
    if profile.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise P146CliError("p146_release_profile_schema_required")
    corpus = profile.get("corpus")
    if not isinstance(corpus, Mapping):
        raise P146CliError("p146_profile_corpus_required")
    return corpus


def _corpus_hash(corpus: Mapping[str, Any]) -> str:
    truth = corpus.get("truth_manifest")
    visible = corpus.get("visible_cases")
    if not isinstance(truth, Mapping) or not isinstance(visible, Sequence) or isinstance(visible, (str, bytes, bytearray)):
        raise P146CliError("p146_corpus_schema_invalid")
    return stable_hash({"visible_cases": list(visible), "truth_manifest": truth})


def _profile_hash(corpus_hash: str) -> str:
    return stable_hash({"schema_version": PROFILE_SCHEMA_VERSION, "corpus_hash": corpus_hash})


def _validate_profile_hashes(profile: Mapping[str, Any], *, corpus_hash: str, profile_hash: str) -> None:
    for key, expected in (("corpus_hash", corpus_hash), ("profile_hash", profile_hash)):
        observed = profile.get(key)
        if observed is not None and observed != expected:
            raise P146CliError(f"p146_{key}_mismatch")
    if profile.get("schema_version") != PROFILE_SCHEMA_VERSION or not SHA256_RE.match(profile_hash) or not SHA256_RE.match(corpus_hash):
        raise P146CliError("p146_profile_hash_contract")


def _select_visible_case(corpus: Mapping[str, Any], case_id: str) -> Mapping[str, Any]:
    visible_cases = corpus.get("visible_cases")
    if not isinstance(visible_cases, Sequence) or isinstance(visible_cases, (str, bytes, bytearray)):
        raise P146CliError("p146_visible_cases_required")
    for visible_case in visible_cases:
        if isinstance(visible_case, Mapping) and visible_case.get("case_id") == case_id:
            return visible_case
    raise P146CliError(f"p146_case_not_found:{case_id}")


def _validate_episode(episode: Any, *, core: Any) -> None:
    episode_map = _mapping(episode, "episode")
    if episode_map.get("schema_version") != "p146.live_shadow_episode.v1":
        raise P146CliError("p146_episode_schema_version")
    request_receipts = _receipt_list(episode_map.get("request_receipts"), "request_receipts", "p146.http_request_receipt.v1")
    response_receipts = _receipt_list(episode_map.get("response_receipts"), "response_receipts", "p146.http_response_receipt.v1")
    if not request_receipts or not response_receipts:
        raise P146CliError("p146_episode_receipts_required")
    counters = _aggregate_counters(episode_map)
    _validate_counter_maps(counters, core=core)
    runtime = counters["runtime"]
    evaluator = counters["evaluator"]
    if runtime["loopback_socket_attempt_count"] != len(request_receipts):
        raise P146CliError("p146_request_receipt_counter_mismatch")
    if runtime["request_commit_count"] != len(request_receipts):
        raise P146CliError("p146_request_commit_counter_mismatch")
    if runtime["request_byte_count"] != sum(_strict_int(receipt.get("request_bytes"), "request_bytes") for receipt in request_receipts):
        raise P146CliError("p146_request_byte_counter_mismatch")
    complete_responses = [receipt for receipt in response_receipts if receipt.get("complete") is True]
    if runtime["complete_response_count"] != len(complete_responses):
        raise P146CliError("p146_response_receipt_counter_mismatch")
    if runtime["response_byte_count"] != sum(_strict_int(receipt.get("observed_bytes"), "observed_bytes") for receipt in complete_responses):
        raise P146CliError("p146_response_byte_counter_mismatch")
    if runtime["provider_record_count"] != sum(_strict_int(receipt.get("record_count"), "record_count") for receipt in complete_responses):
        raise P146CliError("p146_provider_record_counter_mismatch")
    if evaluator["accepted_connection_count"] != len(request_receipts):
        raise P146CliError("p146_accepted_connection_counter_mismatch")
    if evaluator["server_response_count"] != len(complete_responses):
        raise P146CliError("p146_server_response_counter_mismatch")


def _extract_prediction(episode: Any, *, visible_case: Mapping[str, Any], core: Any) -> dict[str, Any]:
    _ = visible_case, core
    if isinstance(episode, Mapping):
        for key in ("prediction", "shadow_prediction", "sealed_prediction"):
            value = episode.get(key)
            if isinstance(value, Mapping):
                return dict(value)
        if episode.get("schema_version") == "p146.shadow_prediction.v1":
            return dict(episode)
    raise P146CliError("p146_core_prediction_missing")


def _build_prediction_artifact(prediction: Mapping[str, Any], *, aggregate_counters: Mapping[str, Any], case_ref_hash: str) -> dict[str, Any]:
    ranked = _sequence(prediction.get("ranked_hypotheses"), "ranked_hypotheses")
    top = _mapping(ranked[0], "top_hypothesis").get("category") if ranked else "insufficient_evidence"
    final_route = _string(prediction.get("final_shadow_route"), "final_shadow_route")
    artifact: dict[str, Any] = {
        "schema_version": "p146.shadow_prediction.v1",
        "case_ref_hash": case_ref_hash,
        "incident_detected": top not in {"healthy", "insufficient_evidence"},
        "diagnostic_disposition": _string(prediction.get("diagnostic_disposition"), "diagnostic_disposition"),
        "ranked_hypotheses": list(ranked),
        "p14_route": _string(prediction.get("p14_route", final_route), "p14_route"),
        "final_shadow_route": final_route,
        "safety_overlay": _string(prediction.get("safety_overlay"), "safety_overlay"),
        "citations": list(_sequence(prediction.get("citations"), "citations")),
        "missing_providers": list(_sequence(prediction.get("missing_providers", ["traces"] if top == "insufficient_evidence" else []), "missing_providers")),
        "executed_actions": list(_sequence(prediction.get("executed_actions"), "executed_actions")),
        "runtime_counters": dict(_mapping(aggregate_counters.get("runtime"), "runtime")),
        "forbidden_counters": dict(_mapping(aggregate_counters.get("forbidden"), "forbidden")),
        "prediction_hash": "",
    }
    _validate_prediction_artifact(artifact)
    artifact["prediction_hash"] = stable_hash({key: value for key, value in artifact.items() if key != "prediction_hash"})
    _validate_prediction_artifact(artifact)
    return artifact


def _validate_prediction_artifact(artifact: Mapping[str, Any]) -> None:
    if tuple(artifact) != PREDICTION_KEYS:
        raise P146CliError("p146_prediction_keyset")
    if artifact.get("schema_version") != "p146.shadow_prediction.v1":
        raise P146CliError("p146_prediction_schema_version")
    if not SHA256_RE.match(_string(artifact.get("case_ref_hash"), "case_ref_hash")):
        raise P146CliError("p146_prediction_case_ref_hash")
    if type(artifact.get("incident_detected")) is not bool:
        raise P146CliError("p146_prediction_incident_bool")
    if artifact.get("executed_actions") != []:
        raise P146CliError("p146_prediction_actions_forbidden")
    _validate_counter_group(_mapping(artifact.get("runtime_counters"), "runtime_counters"), RUNTIME_COUNTER_KEYS, "runtime")
    _validate_counter_group(_mapping(artifact.get("forbidden_counters"), "forbidden_counters"), FORBIDDEN_COUNTER_KEYS, "forbidden")
    if any(artifact["forbidden_counters"][key] != 0 for key in FORBIDDEN_COUNTER_KEYS):
        raise P146CliError("p146_prediction_forbidden_nonzero")


def _build_receipts(
    *,
    case_ref_hash: str,
    corpus_hash: str,
    episode: Mapping[str, Any],
    prediction: Mapping[str, Any],
    profile_hash: str,
) -> dict[str, Any]:
    receipt_artifact = {
        "schema_version": RECEIPTS_SCHEMA_VERSION,
        "case_ref_hash": case_ref_hash,
        "profile_hash": profile_hash,
        "corpus_hash": corpus_hash,
        "request_receipts": list(_receipt_list(episode.get("request_receipts"), "request_receipts", "p146.http_request_receipt.v1")),
        "response_receipts": list(_receipt_list(episode.get("response_receipts"), "response_receipts", "p146.http_response_receipt.v1")),
        "aggregate_counters": dict(_aggregate_counters(episode)),
        "episode_hash": _episode_hash(episode),
        "prediction_hash": stable_hash(prediction),
        "receipts_hash": "",
    }
    receipt_artifact["receipts_hash"] = stable_hash({key: value for key, value in receipt_artifact.items() if key != "receipts_hash"})
    return receipt_artifact


def _forbidden_counters_from_episode(episode: Any) -> dict[str, int]:
    counters = _mapping(_aggregate_counters(_mapping(episode, "episode")).get("forbidden"), "forbidden")
    _validate_counter_group(counters, FORBIDDEN_COUNTER_KEYS, "forbidden")
    return dict(counters)


def _aggregate_counters(episode: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(episode.get("aggregate_counters"), "aggregate_counters")


def _validate_counter_maps(counters: Mapping[str, Any], *, core: Any) -> None:
    validate_counter_maps = getattr(core, "validate_counter_maps", None)
    if callable(validate_counter_maps):
        validate_counter_maps(counters)
    if tuple(counters) != COUNTER_GROUPS:
        raise P146CliError("p146_counter_group_keyset")
    for group, keys in COUNTER_KEYS.items():
        _validate_counter_group(_mapping(counters.get(group), group), keys, group)
    if any(counters["forbidden"][key] != 0 for key in FORBIDDEN_COUNTER_KEYS):
        raise P146CliError("p146_forbidden_counter_nonzero")


def _validate_counter_group(counters: Mapping[str, Any], keys: Sequence[str], label: str) -> None:
    if tuple(counters) != tuple(keys):
        raise P146CliError(f"p146_{label}_counter_keyset")
    for key in keys:
        _strict_int(counters.get(key), key)


def _receipt_list(value: Any, label: str, schema_version: str) -> Sequence[Mapping[str, Any]]:
    receipts = _sequence(value, label)
    if not receipts:
        raise P146CliError(f"p146_{label}_required")
    for receipt in receipts:
        receipt_map = _mapping(receipt, label)
        if receipt_map.get("schema_version") != schema_version:
            raise P146CliError(f"p146_{label}_schema_version")
    return receipts


def _episode_hash(episode: Mapping[str, Any]) -> str:
    observed = episode.get("episode_hash")
    expected = stable_hash({key: value for key, value in episode.items() if key != "episode_hash"})
    if observed is not None and observed != expected:
        raise P146CliError("p146_episode_hash_mismatch")
    return expected


def _strict_int(value: Any, key: str) -> int:
    if type(value) is not int:
        raise P146CliError(f"p146_counter_int_required:{key}")
    return value


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P146CliError(f"{label}_object_required")
    return value


def _sequence(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise P146CliError(f"{label}_sequence_required")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or value == "":
        raise P146CliError(f"{label}_string_required")
    return value


def _prepare_output_dir(path: Path) -> Path:
    if path.is_symlink():
        raise P146CliError("p146_output_symlink_forbidden")
    parent = path.parent
    if not parent.exists() or parent.is_symlink() or not parent.is_dir():
        raise P146CliError("p146_output_parent_boundary_invalid")
    resolved_parent = parent.resolve(strict=True)
    path.mkdir(parents=False, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise P146CliError("p146_output_boundary_invalid")
    resolved_output = path.resolve(strict=True)
    if resolved_output.parent != resolved_parent:
        raise P146CliError("p146_output_boundary_escape")
    return path


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    data = (_canonical_json(value) + "\n").encode("utf-8")
    _scan_artifact_bytes(data)
    if path.is_symlink():
        raise P146CliError("p146_artifact_symlink_forbidden")
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        if tmp_path.exists() or tmp_path.is_symlink():
            raise P146CliError("p146_artifact_temp_collision")
        tmp_path.write_bytes(data)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _canonical_json(value: Any) -> str:
    return json.dumps(_json_ready(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, frozenset | set):
        return [_json_ready(item) for item in sorted(value, key=repr)]
    if isinstance(value, Path):
        return value.name
    return value


def _scan_artifact_bytes(data: bytes) -> None:
    text = data.decode("utf-8")
    lowered = text.lower()
    parsed = json.loads(text, object_pairs_hook=_strict_json_object)
    for marker in LEAK_TEXT_MARKERS:
        if marker in lowered:
            raise P146CliError(f"p146_artifact_forbidden_text:{marker}")
    for path in (Path.cwd(), Path.home(), Path("/tmp"), Path("/private/tmp")):
        path_text = str(path)
        if path_text and path_text in text:
            raise P146CliError("p146_artifact_absolute_path")
    _scan_artifact_value(parsed)


def _scan_artifact_value(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered_key = str(key).lower()
            if lowered_key in LEAK_KEY_MARKERS or (
                lowered_key.endswith("_bytes")
                and lowered_key not in {"request_bytes", "declared_bytes", "observed_bytes", *RUNTIME_COUNTER_KEYS, *EVALUATOR_COUNTER_KEYS, *RESOURCE_COUNTER_KEYS}
            ):
                raise P146CliError(f"p146_artifact_forbidden_key:{key}")
            _scan_artifact_value(item)
    elif isinstance(value, list):
        for item in value:
            _scan_artifact_value(item)
    elif isinstance(value, str):
        lowered = value.lower()
        if value.startswith(("/Users/", "/private/", "/tmp/", "file:")):
            raise P146CliError("p146_artifact_absolute_path")
        for marker in ("authorization", "password", "secret", "api_key", "apikey", "credential", "raw_bytes"):
            if marker in lowered:
                raise P146CliError(f"p146_artifact_forbidden_value:{marker}")


if __name__ == "__main__":
    raise SystemExit(main())
