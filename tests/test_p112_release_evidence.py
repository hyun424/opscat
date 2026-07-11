from __future__ import annotations

from app.services.p112_release_evidence import produce_p112_release_evidence, request_envelope_complete


def _metric(value: float) -> dict[str, float | int]:
    return {"value": value, "numerator": int(value * 100), "denominator": 100}


def _comparison() -> dict[str, object]:
    metrics = {
        "service_top1": _metric(0.84),
        "service_top3": _metric(0.92),
        "fault_accuracy": _metric(0.84),
        "evidence_precision": _metric(0.95),
    }
    return {
        "benchmark_role": "blind",
        "comparison_hash": "sha256:test",
        "candidate_metrics": metrics,
        "candidate_by_fault": {
            "loss": {"metrics": {"fault_accuracy": _metric(0.60)}},
            "delay": {"metrics": {"fault_accuracy": _metric(0.60)}},
        },
        "metric_deltas": {"service_top1": 0.04, "fault_accuracy": 0.0},
        "zero_safety_counters": True,
    }


def test_release_remains_fail_closed_without_crypto_review() -> None:
    release = produce_p112_release_evidence(
        comparison=_comparison(),
        repeat_agreement={"joint_agreement": 0.90},
        freeze_verified=True,
        replay_integrity={
            "baseline_request_complete": True,
            "candidate_request_complete": True,
            "baseline_raw_replay": True,
            "candidate_raw_replay": True,
            "candidate_repeat_raw_replay": True,
        },
    )
    assert release["release_qualified"] is False
    assert release["gates"]["cryptographic_review"] is False
    assert release["action_execution_enabled"] is False


def test_release_passes_only_with_all_gates_and_crypto_review() -> None:
    release = produce_p112_release_evidence(
        comparison=_comparison(),
        repeat_agreement={"joint_agreement": 0.90},
        freeze_verified=True,
        replay_integrity={
            "baseline_request_complete": True,
            "candidate_request_complete": True,
            "baseline_raw_replay": True,
            "candidate_raw_replay": True,
            "candidate_repeat_raw_replay": True,
        },
        cryptographic_review={
            "schema_version": "p112.cryptographic_review.v1",
            "signature_verified": True,
            "provider_receipts_verified": True,
        },
    )
    assert release["release_qualified"] is True
    assert release["action_execution_enabled"] is False


def test_request_envelope_requires_every_pinned_field() -> None:
    request = {
        "model": "model",
        "provider_endpoint": "https://example.test/v1",
        "provider_api": "api",
        "system_prompt_sha256": "abc",
        "prompt_schema_version": "v1",
        "decoding_config": {},
    }
    assert request_envelope_complete(request)
    request.pop("system_prompt_sha256")
    assert not request_envelope_complete(request)


def test_repeat_raw_replay_is_a_hard_gate() -> None:
    release = produce_p112_release_evidence(
        comparison=_comparison(),
        repeat_agreement={"joint_agreement": 1.0},
        freeze_verified=True,
        replay_integrity={
            "baseline_request_complete": True,
            "candidate_request_complete": True,
            "baseline_raw_replay": True,
            "candidate_raw_replay": True,
            "candidate_repeat_raw_replay": False,
        },
        cryptographic_review={
            "schema_version": "p112.cryptographic_review.v1",
            "signature_verified": True,
            "provider_receipts_verified": True,
        },
    )
    assert release["release_qualified"] is False
    assert release["gates"]["candidate_repeat_raw_replay"] is False
