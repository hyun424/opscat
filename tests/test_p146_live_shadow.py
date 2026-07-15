from __future__ import annotations

import copy
import pickle
from pathlib import Path

import pytest

from tests.fixtures.p146.builders import (
    EVALUATOR_COUNTER_KEYS,
    FORBIDDEN_COUNTER_KEYS,
    P146_CLOSED_CATEGORIES,
    RESOURCE_COUNTER_KEYS,
    RUNTIME_COUNTER_KEYS,
    build_known_conformance_corpus,
    exact_wire_requests,
    expected_confusion,
    expected_denominators,
    semantic_rebind_case,
)


def test_capability_is_process_owned_numeric_loopback_and_unserializable() -> None:
    from app.services.p146_live_shadow import (
        P146LiveShadowError,
        issue_process_owned_capability,
        validate_capability,
    )

    capability = issue_process_owned_capability()
    assert capability.address == "127.0.0.1"
    assert capability.port > 0
    assert capability.family == "AF_INET"
    assert validate_capability(capability)["ok"] is True
    with pytest.raises((TypeError, pickle.PicklingError, P146LiveShadowError)):
        pickle.dumps(capability)
    forged = copy.copy(capability)
    forged.nonce = "0" * 64
    with pytest.raises(P146LiveShadowError, match="capability|nonce|hash"):
        validate_capability(forged)
    capability.listener.close()
    with pytest.raises(P146LiveShadowError, match="closed|liveness"):
        validate_capability(capability)


def test_wire_contract_is_exact_and_rejects_protocol_variants() -> None:
    from app.services.p146_live_shadow import (
        P146LiveShadowError,
        build_observation_get_requests,
        validate_observation_request_bytes,
    )

    expected = exact_wire_requests(49152)
    observed = build_observation_get_requests(port=49152)
    assert observed == expected
    for request in observed:
        assert validate_observation_request_bytes(request, port=49152)["ok"] is True
    variants = (
        expected[0].replace(b"query,start,end,step", b""),
        expected[0].replace(b"GET ", b"POST ", 1),
        expected[1].replace(b"direction=forward", b"direction=backward"),
        expected[2].replace(b"Connection: close\r\n", b"Connection: close\r\nX-Extra: no\r\n"),
        expected[2].replace(b"\r\n", b"\n"),
    )
    for request in variants:
        with pytest.raises(P146LiveShadowError, match="request|wire|contract"):
            validate_observation_request_bytes(request, port=49152)


def test_p135_backed_prometheus_and_loki_normalization() -> None:
    from app.services.p110_evaluation import stable_hash
    from app.services.p146_live_shadow import normalize_provider_response_bytes

    corpus = build_known_conformance_corpus()
    visible = corpus["visible_cases"][0]
    prometheus_bytes = b'{"status":"success","data":{"resultType":"matrix","result":[]}}'
    loki_bytes = b'{"status":"success","data":{"resultType":"streams","result":[]}}'
    prometheus_records = normalize_provider_response_bytes(
        prometheus_bytes,
        provider="prometheus",
        format_name="prometheus.query_range.matrix.v1",
        source_id=visible["prometheus"]["source_id"],
        ingested_at="2026-07-15T00:00:00Z",
        limits={"max_records_per_artifact": 256, "max_string_bytes": 128},
        raw_sha256=stable_hash(prometheus_bytes),
    )
    loki_records = normalize_provider_response_bytes(
        loki_bytes,
        provider="loki",
        format_name="loki.query_range.streams.v1",
        source_id=visible["loki"]["source_id"],
        ingested_at="2026-07-15T00:00:00Z",
        limits={"max_records_per_artifact": 256, "max_string_bytes": 128},
        raw_sha256=stable_hash(loki_bytes),
    )
    assert all("_p135_record" not in record for record in prometheus_records + loki_records)
    assert all("raw_bytes" not in str(record).lower() for record in prometheus_records + loki_records)


def test_trace_delta_validation_and_redaction() -> None:
    from app.services.p146_live_shadow import P146LiveShadowError, canonicalize_visible_case, validate_trace_response

    visible = build_known_conformance_corpus()["visible_cases"][0]
    trace = visible["traces"]
    validated = validate_trace_response(trace)
    assert validated["schema_version"] == "p146.otel_trace_response.v1"
    assert "raw" not in str(canonicalize_visible_case(visible)).lower()
    forged = copy.deepcopy(trace)
    forged["spans"][0]["attributes"]["authorization"] = "secret-token"
    with pytest.raises(P146LiveShadowError, match="attribute|secret|schema"):
        validate_trace_response(forged)


def test_closed_lattice_ranks_complete_faults_and_abstains_on_gaps() -> None:
    from app.services.p146_live_shadow import rank_hypotheses_for_visible_case

    corpus = build_known_conformance_corpus()
    rows = {row["case_id"]: row for row in corpus["truth_manifest"]["rows"]}
    for visible in corpus["visible_cases"]:
        prediction = rank_hypotheses_for_visible_case(visible)
        top = prediction["ranked_hypotheses"][0]["category"]
        assert top in P146_CLOSED_CATEGORIES
        truth = rows[visible["case_id"]]
        if "gap" in truth["slices"]:
            assert top == "insufficient_evidence"
        elif truth["cause_truth"] == "healthy":
            assert top == "healthy"
        else:
            assert truth["cause_truth"] in [item["category"] for item in prediction["ranked_hypotheses"][:3]]
            assert all(citation in prediction["citations"] for citation in prediction["ranked_hypotheses"][0]["citations"])


def test_p14_route_adapter_and_safety_overlay_are_total() -> None:
    from app.services.p146_live_shadow import adapt_p14_route, predict_shadow_case

    assert adapt_p14_route("local_mock_auto_allowed") == "shadow_action_candidate"
    assert adapt_p14_route("approval_required") == "shadow_action_candidate"
    assert adapt_p14_route("human_required") == "human_review_required"
    assert adapt_p14_route("blocked") == "blocked_untrusted_evidence"

    corpus = build_known_conformance_corpus()
    rows = {row["case_id"]: row for row in corpus["truth_manifest"]["rows"]}
    for visible in corpus["visible_cases"]:
        prediction = predict_shadow_case(visible)
        assert prediction["executed_actions"] == []
        assert prediction["final_shadow_route"] == rows[visible["case_id"]]["route_truth"]
        assert all(value == 0 for value in prediction["forbidden_counters"].values())


def test_known_corpus_predictions_ignore_identifiers_hashes_paths_and_truth_pairing() -> None:
    from app.services.p146_live_shadow import predict_shadow_case, score_sealed_predictions

    corpus = build_known_conformance_corpus()
    first = corpus["visible_cases"][0]
    baseline = predict_shadow_case(first)
    rebound = predict_shadow_case(semantic_rebind_case(first))
    assert rebound["ranked_hypotheses"] == baseline["ranked_hypotheses"]
    assert rebound["diagnostic_disposition"] == baseline["diagnostic_disposition"]
    reordered_truth = copy.deepcopy(corpus["truth_manifest"])
    reordered_truth["rows"] = list(reversed(reordered_truth["rows"]))
    assert score_sealed_predictions([baseline], corpus["truth_manifest"]) == score_sealed_predictions([baseline], reordered_truth)
    mismatched_truth = copy.deepcopy(corpus["truth_manifest"])
    mismatched_truth["rows"][0]["cause_truth"] = "healthy"
    assert predict_shadow_case(first) == baseline
    assert score_sealed_predictions([baseline], mismatched_truth) != score_sealed_predictions([baseline], corpus["truth_manifest"])


def test_benchmark_confusion_slices_calibration_and_replay() -> None:
    from app.services.p146_live_shadow import run_known_conformance_benchmark

    report = run_known_conformance_benchmark(build_known_conformance_corpus(), monotonic_ns=lambda: 1_000_000)
    assert report["denominators"] == expected_denominators()
    assert report["confusion"] == expected_confusion()
    assert report["descriptive_metrics"]["precision"] == 1.0
    assert report["descriptive_metrics"]["recall"] == 1.0
    assert report["descriptive_metrics"]["f1"] == 1.0
    assert report["descriptive_metrics"]["false_positive_rate"] == 0.0
    assert report["slices"]["gap"]["abstention"] == {"passed": 8, "total": 8}
    assert report["slices"]["injection"]["contained"] == {"passed": 8, "total": 8}
    replay = run_known_conformance_benchmark(build_known_conformance_corpus(), monotonic_ns=lambda: 1_000_000)
    assert replay["semantic_prediction_hash"] == report["semantic_prediction_hash"]


def test_closed_counters_reconcile_and_forbidden_authority_is_zero() -> None:
    from app.services.p146_live_shadow import run_live_shadow_episode, validate_counter_maps

    episode = run_live_shadow_episode(build_known_conformance_corpus()["visible_cases"][40])
    validate_counter_maps(episode["aggregate_counters"])
    counters = episode["aggregate_counters"]
    assert tuple(counters["runtime"]) == RUNTIME_COUNTER_KEYS
    assert tuple(counters["evaluator"]) == EVALUATOR_COUNTER_KEYS
    assert tuple(counters["resources"]) == RESOURCE_COUNTER_KEYS
    assert tuple(counters["forbidden"]) == FORBIDDEN_COUNTER_KEYS
    for group in counters.values():
        assert all(type(value) is int for value in group.values())
    assert counters["runtime"]["loopback_socket_attempt_count"] == 3
    assert counters["runtime"]["complete_response_count"] == 2
    assert counters["evaluator"]["accepted_connection_count"] == 3
    assert counters["evaluator"]["server_response_count"] == 2
    assert counters["forbidden"] == {key: 0 for key in FORBIDDEN_COUNTER_KEYS}
    assert not any(Path(".").glob("evals/p146/output/*"))

