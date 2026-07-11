"""Fail-closed paired baseline/candidate freeze contract for P112."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.services.p110_evaluation import stable_hash

SCHEMA_VERSION = "p112.paired_freeze.v1"


class P112FreezeError(ValueError):
    """Raised when a P112 blind request differs from the frozen inputs."""


def build_p112_freeze(
    *,
    model_artifact_hash: str,
    implementation_hash: str,
    training_source_hashes: Sequence[str],
    blind_source_hash: str,
    baseline_packets: Sequence[Mapping[str, Any]],
    candidate_packets: Sequence[Mapping[str, Any]],
    baseline_request: Mapping[str, Any],
    candidate_request: Mapping[str, Any],
    acceptance_gates: Mapping[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "frozen",
        "benchmark_role": "blind",
        "blind_repetition": 4,
        "model_artifact_hash": model_artifact_hash,
        "implementation_hash": implementation_hash,
        "training_source_hashes": sorted(str(item) for item in training_source_hashes),
        "blind_source_hash": blind_source_hash,
        "baseline_packets_hash": stable_hash({str(item["case_id"]): item for item in baseline_packets}),
        "candidate_packets_hash": stable_hash({str(item["case_id"]): item for item in candidate_packets}),
        "blind_case_ids_hash": stable_hash(sorted(str(item["case_id"]) for item in candidate_packets)),
        "baseline_request": dict(baseline_request),
        "candidate_request": dict(candidate_request),
        "acceptance_gates": dict(acceptance_gates),
    }
    _validate_request(payload["baseline_request"], name="baseline")
    _validate_request(payload["candidate_request"], name="candidate")
    payload["freeze_hash"] = stable_hash(payload)
    return payload


def validate_p112_freeze(
    frozen: Mapping[str, Any],
    *,
    model_artifact_hash: str,
    implementation_hash: str,
    training_source_hashes: Sequence[str],
    blind_source_hash: str,
    baseline_packets: Sequence[Mapping[str, Any]],
    candidate_packets: Sequence[Mapping[str, Any]],
    baseline_request: Mapping[str, Any],
    candidate_request: Mapping[str, Any],
) -> None:
    if frozen.get("schema_version") != SCHEMA_VERSION or frozen.get("status") != "frozen":
        raise P112FreezeError("invalid_freeze_manifest")
    submitted_hash = str(frozen.get("freeze_hash", ""))
    unhashed = {key: value for key, value in frozen.items() if key != "freeze_hash"}
    if submitted_hash != stable_hash(unhashed):
        raise P112FreezeError("freeze_manifest_tampered")
    expected = build_p112_freeze(
        model_artifact_hash=model_artifact_hash,
        implementation_hash=implementation_hash,
        training_source_hashes=training_source_hashes,
        blind_source_hash=blind_source_hash,
        baseline_packets=baseline_packets,
        candidate_packets=candidate_packets,
        baseline_request=baseline_request,
        candidate_request=candidate_request,
        acceptance_gates=frozen.get("acceptance_gates", {}),
    )
    for key, value in expected.items():
        if key == "freeze_hash":
            continue
        if frozen.get(key) != value:
            raise P112FreezeError(f"freeze_mismatch:{key}")


def _validate_request(value: Any, *, name: str) -> None:
    if not isinstance(value, Mapping):
        raise P112FreezeError(f"invalid_{name}_request")
    required = {
        "model",
        "provider_endpoint",
        "provider_api",
        "system_prompt_sha256",
        "prompt_schema_version",
        "decoding_config",
    }
    missing = sorted(required - set(str(key) for key in value))
    if missing:
        raise P112FreezeError(f"missing_{name}_request_field:{missing[0]}")
