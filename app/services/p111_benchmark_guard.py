"""P111 benchmark split and configuration-freeze guardrails."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.services.p110_evaluation import stable_hash

SCHEMA_VERSION = "p111.benchmark_freeze.v1"
ROLE_BY_REPETITION: Mapping[int, str] = {
    1: "development",
    2: "validation",
    3: "blind",
    4: "reserve",
    5: "contaminated_baseline",
}
_SELECTION_ROLES = frozenset({"development", "validation"})


class P111BenchmarkGuardError(ValueError):
    """Raised when P111 benchmark governance is violated."""


def benchmark_role(repetition: int) -> str:
    try:
        return ROLE_BY_REPETITION[repetition]
    except KeyError as exc:
        raise P111BenchmarkGuardError(f"unsupported_repetition:{repetition}") from exc


def create_freeze_manifest(
    *,
    selected_on_repetition: int,
    model: str,
    prompt_schema_version: str,
    decoding_config: Mapping[str, Any],
    implementation_hash: str,
    official_source_hash: str,
    candidate_packets: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    selected_on_role = benchmark_role(selected_on_repetition)
    if selected_on_role not in _SELECTION_ROLES:
        raise P111BenchmarkGuardError(f"selection_on_protected_role:{selected_on_role}")
    if not model or not prompt_schema_version or not implementation_hash:
        raise P111BenchmarkGuardError("incomplete_configuration")
    if not official_source_hash.startswith("sha256:"):
        raise P111BenchmarkGuardError("invalid_official_source_hash")
    case_ids = sorted(str(packet.get("case_id", "")) for packet in candidate_packets)
    if not case_ids or any(not case_id for case_id in case_ids) or len(case_ids) != len(set(case_ids)):
        raise P111BenchmarkGuardError("invalid_candidate_packet_set")
    body = {
        "schema_version": SCHEMA_VERSION,
        "status": "frozen",
        "selected_on_repetition": selected_on_repetition,
        "selected_on_role": selected_on_role,
        "model": model,
        "prompt_schema_version": prompt_schema_version,
        "decoding_config": _stable(decoding_config),
        "implementation_hash": implementation_hash,
        "official_source_hash": official_source_hash,
        "candidate_packet_hash": stable_hash({str(packet["case_id"]): packet for packet in candidate_packets}),
        "case_ids_hash": stable_hash(case_ids),
    }
    body["freeze_hash"] = stable_hash(body)
    return body


def validate_frozen_run(
    manifest: Mapping[str, Any],
    *,
    target_repetition: int,
    model: str,
    prompt_schema_version: str,
    decoding_config: Mapping[str, Any],
    implementation_hash: str,
    official_source_hash: str,
    candidate_packets: Sequence[Mapping[str, Any]],
) -> str:
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("status") != "frozen":
        raise P111BenchmarkGuardError("invalid_freeze_manifest")
    submitted_hash = str(manifest.get("freeze_hash", ""))
    unhashed = {key: value for key, value in manifest.items() if key != "freeze_hash"}
    if submitted_hash != stable_hash(unhashed):
        raise P111BenchmarkGuardError("freeze_manifest_tampered")
    role = benchmark_role(target_repetition)
    expected = {
        "model": model,
        "prompt_schema_version": prompt_schema_version,
        "decoding_config": _stable(decoding_config),
        "implementation_hash": implementation_hash,
        "official_source_hash": official_source_hash,
        "candidate_packet_hash": stable_hash({str(packet["case_id"]): packet for packet in candidate_packets}),
        "case_ids_hash": stable_hash(sorted(str(packet.get("case_id", "")) for packet in candidate_packets)),
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise P111BenchmarkGuardError(f"frozen_configuration_mismatch:{key}")
    if role == "reserve":
        raise P111BenchmarkGuardError("reserve_set_requires_separate_promotion")
    return role


def _stable(value: Any) -> Any:
    import json

    return json.loads(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str))
