from __future__ import annotations

import copy

import pytest

from app.services.p112_freeze_guard import P112FreezeError, build_p112_freeze, validate_p112_freeze


def _request(schema: str) -> dict:
    return {
        "model": "model",
        "provider_endpoint": "https://example.invalid/v1",
        "provider_api": "chat",
        "system_prompt_sha256": "1" * 64,
        "prompt_schema_version": schema,
        "decoding_config": {"temperature": 0},
    }


def _packets(prefix: str) -> list[dict]:
    return [{"case_id": f"{prefix}-{index}", "packet": index} for index in range(2)]


def _freeze() -> dict:
    return build_p112_freeze(
        model_artifact_hash="sha256:" + "1" * 64,
        implementation_hash="sha256:" + "2" * 64,
        training_source_hashes=("sha256:" + "3" * 64, "sha256:" + "4" * 64),
        blind_source_hash="sha256:" + "4" * 64,
        baseline_packets=_packets("base"),
        candidate_packets=_packets("cand"),
        baseline_request=_request("baseline.v1"),
        candidate_request=_request("candidate.v1"),
        acceptance_gates={"service_top1_min": 0.84},
    )


def test_freeze_binds_both_complete_request_envelopes() -> None:
    frozen = _freeze()
    validate_p112_freeze(
        frozen,
        model_artifact_hash="sha256:" + "1" * 64,
        implementation_hash="sha256:" + "2" * 64,
        training_source_hashes=("sha256:" + "3" * 64, "sha256:" + "4" * 64),
        blind_source_hash="sha256:" + "4" * 64,
        baseline_packets=_packets("base"),
        candidate_packets=_packets("cand"),
        baseline_request=_request("baseline.v1"),
        candidate_request=_request("candidate.v1"),
    )


def test_freeze_rejects_packet_and_endpoint_changes() -> None:
    frozen = _freeze()
    request = _request("candidate.v1")
    request["provider_endpoint"] = "https://changed.invalid/v1"
    with pytest.raises(P112FreezeError, match="candidate_request"):
        validate_p112_freeze(
            frozen,
            model_artifact_hash="sha256:" + "1" * 64,
            implementation_hash="sha256:" + "2" * 64,
            training_source_hashes=("sha256:" + "3" * 64, "sha256:" + "4" * 64),
            blind_source_hash="sha256:" + "4" * 64,
            baseline_packets=_packets("base"),
            candidate_packets=_packets("cand"),
            baseline_request=_request("baseline.v1"),
            candidate_request=request,
        )


def test_freeze_rejects_tampering_and_missing_baseline_binding() -> None:
    tampered = copy.deepcopy(_freeze())
    del tampered["baseline_request"]["system_prompt_sha256"]
    with pytest.raises(P112FreezeError, match="tampered"):
        validate_p112_freeze(
            tampered,
            model_artifact_hash="sha256:" + "1" * 64,
            implementation_hash="sha256:" + "2" * 64,
            training_source_hashes=("sha256:" + "3" * 64, "sha256:" + "4" * 64),
            blind_source_hash="sha256:" + "4" * 64,
            baseline_packets=_packets("base"),
            candidate_packets=_packets("cand"),
            baseline_request=_request("baseline.v1"),
            candidate_request=_request("candidate.v1"),
        )
