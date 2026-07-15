from __future__ import annotations

import copy
import hashlib
import json
import pickle
import socket
from pathlib import Path
from types import SimpleNamespace
from typing import Any

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


def _normative_trace_payload() -> dict[str, Any]:
    from app.services.p110_evaluation import stable_hash

    trace = {
        "schema_version": "p146.otel_trace_response.v1",
        "resource_spans": [
            {
                "resource": {"service_name": "checkout"},
                "spans": [
                    {
                        "trace_id": "0" * 32,
                        "span_id": "1" * 16,
                        "parent_span_id": "",
                        "name": "http.handler",
                        "start_ms": 0,
                        "end_ms": 700,
                        "status": "error",
                        "attributes": {"server.address": "127.0.0.1"},
                    }
                ],
            }
        ],
        "response_hash": "",
    }
    trace["response_hash"] = stable_hash({key: value for key, value in trace.items() if key != "response_hash"})
    return trace


def _healthy_wire_responses() -> tuple[bytes, bytes, bytes]:
    prom = {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [
                {"metric": {"__name__": "opscat_incident_signals", "signal": "error_rate_bps"}, "values": [[0, "0"]]},
                {"metric": {"__name__": "opscat_incident_signals", "signal": "db_pool_saturation_bps"}, "values": [[0, "0"]]},
                {"metric": {"__name__": "opscat_incident_signals", "signal": "dependency_timeout_bps"}, "values": [[0, "0"]]},
                {"metric": {"__name__": "opscat_incident_signals", "signal": "queue_depth"}, "values": [[0, "0"]]},
                {"metric": {"__name__": "opscat_incident_signals", "signal": "cpu_usage_bps"}, "values": [[0, "1000"]]},
                {"metric": {"__name__": "opscat_incident_signals", "signal": "memory_usage_bps"}, "values": [[0, "1000"]]},
                {"metric": {"__name__": "opscat_incident_signals", "signal": "retry_rate_bps"}, "values": [[0, "0"]]},
                {"metric": {"__name__": "opscat_incident_signals", "signal": "db_query_p95_ms"}, "values": [[0, "30"]]},
            ],
        },
    }
    loki = {"status": "success", "data": {"resultType": "streams", "result": [{"stream": {"job": "opscat-lab"}, "values": [["0", "steady_state"]]}]}}
    trace = {
        "schema_version": "p146.otel_trace_response.v1",
        "resource_spans": [
            {
                "resource": {"service_name": "opscat-lab"},
                "spans": [
                    {
                        "trace_id": "0" * 32,
                        "span_id": "1" * 16,
                        "parent_span_id": "",
                        "name": "http.handler",
                        "start_ms": 0,
                        "end_ms": 30,
                        "status": "ok",
                        "attributes": {},
                    }
                ],
            }
        ],
    }
    from app.services.p110_evaluation import stable_hash

    trace["response_hash"] = stable_hash(trace)

    def response(body: dict[str, Any]) -> bytes:
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
        return (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
            + str(len(encoded)).encode("ascii")
            + b"\r\nConnection: close\r\n\r\n"
            + encoded
        )

    return response(prom), response(loki), response(trace)


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
        assert validate_observation_request_bytes(request, port=49152)["ok"] is True
    variants = (
        expected[0].replace(b"query=opscat_incident_signals&", b""),
        expected[0].replace(b"GET ", b"POST ", 1),
        expected[1].replace(b"direction=forward", b"direction=backward"),
        expected[2].replace(b"Connection: close\r\n", b"Connection: close\r\nX-Extra: no\r\n"),
        expected[2].replace(b"\r\n", b"\n"),
    )
    for request in variants:
        with pytest.raises(P146LiveShadowError, match="request|wire|contract"):
            validate_observation_request_bytes(request, port=49152)


def test_p135_backed_prometheus_and_loki_normalization() -> None:
    from app.services.p146_live_shadow import P146LiveShadowError, normalize_provider_response_bytes

    corpus = build_known_conformance_corpus()
    visible = corpus["visible_cases"][0]
    prometheus_bytes = (
        b'{"status":"success","data":{"resultType":"matrix","result":[{"metric":{"__name__":"opscat_incident_signals",'
        b'"signal":"error_rate_bps"},"values":[[0,"601"],[15,"602"]]}]}}'
    )
    loki_bytes = (
        b'{"status":"success","data":{"resultType":"streams","result":[{"stream":{"job":"opscat-lab"},'
        b'"values":[["0","release_change"],["1","http.handler error"]]}]}}'
    )
    prometheus_records = normalize_provider_response_bytes(
        prometheus_bytes,
        provider="prometheus",
        format_name="prometheus.query_range.matrix.v1",
        source_id=visible["prometheus"]["source_id"],
        ingested_at="2026-07-15T00:00:00Z",
        limits={"max_records_per_artifact": 256, "max_string_bytes": 128},
        raw_sha256="sha256:" + hashlib.sha256(prometheus_bytes).hexdigest(),
    )
    loki_records = normalize_provider_response_bytes(
        loki_bytes,
        provider="loki",
        format_name="loki.query_range.streams.v1",
        source_id=visible["loki"]["source_id"],
        ingested_at="2026-07-15T00:00:00Z",
        limits={"max_records_per_artifact": 256, "max_string_bytes": 128},
        raw_sha256="sha256:" + hashlib.sha256(loki_bytes).hexdigest(),
    )
    assert all("schema_version" not in record for record in prometheus_records + loki_records)
    assert all("telemetry_record_id" in record for record in prometheus_records + loki_records)
    assert all("p120_record" not in record for record in prometheus_records + loki_records)
    assert all("_p135_record" not in record for record in prometheus_records + loki_records)
    assert all("raw_bytes" not in str(record).lower() for record in prometheus_records + loki_records)
    with pytest.raises(P146LiveShadowError, match="unsupported_provider_format|provider_schema_mismatch"):
        normalize_provider_response_bytes(
            prometheus_bytes,
            provider="loki",
            format_name="loki.query_range.streams.v1",
            source_id=visible["loki"]["source_id"],
            ingested_at="2026-07-15T00:00:00Z",
            limits={"max_records_per_artifact": 256, "max_string_bytes": 128},
            raw_sha256="sha256:" + hashlib.sha256(prometheus_bytes).hexdigest(),
        )
    with pytest.raises(P146LiveShadowError, match="record_budget_exceeded"):
        normalize_provider_response_bytes(
            prometheus_bytes,
            provider="prometheus",
            format_name="prometheus.query_range.matrix.v1",
            source_id=visible["prometheus"]["source_id"],
            ingested_at="2026-07-15T00:00:00Z",
            limits={"max_records_per_artifact": 1, "max_string_bytes": 128},
            raw_sha256="sha256:" + hashlib.sha256(prometheus_bytes).hexdigest(),
        )


def test_trace_delta_validation_and_redaction() -> None:
    from app.services.p146_live_shadow import P146LiveShadowError, canonicalize_visible_case, validate_trace_response

    visible = build_known_conformance_corpus()["visible_cases"][0]
    assert set(visible["traces"]) == {"schema_version", "resource_spans", "response_hash"}
    legacy_trace = {
        "schema_version": "p146.otel_trace_response.v1",
        "source_id": "legacy-trace",
        "observed_at_ms": 0,
        "spans": visible["traces"]["resource_spans"][0]["spans"],
    }
    with pytest.raises(P146LiveShadowError, match="trace|schema|keyset"):
        validate_trace_response(legacy_trace)
    trace = _normative_trace_payload()
    validated = validate_trace_response(trace)
    assert validated == trace
    wrong_hash: Any = copy.deepcopy(trace)
    wrong_hash["response_hash"] = "sha256:" + "0" * 64
    with pytest.raises(P146LiveShadowError, match="trace|response_hash|hash"):
        validate_trace_response(wrong_hash)
    assert "raw" not in str(canonicalize_visible_case(visible)).lower()
    forged: Any = copy.deepcopy(trace)
    forged["resource_spans"][0]["spans"][0]["attributes"]["authorization"] = "secret-token"
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
        assert all("provider_count" in item and "hypothesis_hash" in item for item in prediction["ranked_hypotheses"])

    weak_one_provider = copy.deepcopy(corpus["visible_cases"][0])
    weak_one_provider["prometheus"]["signals"]["error_rate_bps"] = 499
    weak_one_provider["loki"]["markers"] = ["steady_state"]
    weak_one_provider["traces"] = None
    prediction = rank_hypotheses_for_visible_case(weak_one_provider)
    assert prediction["ranked_hypotheses"][0]["category"] == "insufficient_evidence"


def test_appendix_c_lattice_uses_exact_edges_weights_and_tiebreaks() -> None:
    from app.services.p146_live_shadow import rank_hypotheses_for_visible_case

    visible = build_known_conformance_corpus()["visible_cases"][0]
    ranked = rank_hypotheses_for_visible_case(visible)["ranked_hypotheses"]
    deploy = next(item for item in ranked if item["category"] == "deploy_regression")
    assert deploy["score_bps"] == 9000
    assert deploy["provider_count"] == 3
    assert deploy["support_edges"] == ["m.deploy.error", "l.deploy.marker", "t.deploy.handler"]
    assert deploy["contradiction_edges"] == []

    one_provider_tie = copy.deepcopy(visible)
    one_provider_tie["prometheus"]["signals"] = {key: 0 for key in one_provider_tie["prometheus"]["signals"]}
    one_provider_tie["prometheus"]["signals"]["cpu_usage_bps"] = 1000
    one_provider_tie["prometheus"]["signals"]["memory_usage_bps"] = 1000
    one_provider_tie["prometheus"]["signals"]["db_query_p95_ms"] = 30
    one_provider_tie["loki"]["markers"] = ["release_change", "upstream_timeout"]
    one_provider_tie["traces"]["resource_spans"][0]["spans"][0]["status"] = "ok"
    ranked_tie = rank_hypotheses_for_visible_case(one_provider_tie)["ranked_hypotheses"]
    assert ranked_tie[0]["category"] == "insufficient_evidence"


def test_p14_route_adapter_and_safety_overlay_are_total(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.p146_live_shadow as live_shadow
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

    def blocked_judgment(_context: object, *, provider: object) -> SimpleNamespace:
        return SimpleNamespace(to_dict=lambda: {"safety_gate": {"final_route": "blocked"}, "citations": []})

    monkeypatch.setattr(live_shadow, "run_llm_judgment_from_packet", blocked_judgment)
    blocked_prediction = predict_shadow_case(corpus["visible_cases"][0])
    assert blocked_prediction["p14_route"] == "blocked"
    assert blocked_prediction["final_shadow_route"] == "blocked_untrusted_evidence"

    def human_required_judgment(_context: object, *, provider: object) -> SimpleNamespace:
        return SimpleNamespace(to_dict=lambda: {"safety_gate": {"final_route": "human_required"}, "citations": []})

    monkeypatch.setattr(live_shadow, "run_llm_judgment_from_packet", human_required_judgment)
    human_required_prediction = predict_shadow_case(corpus["visible_cases"][0])
    assert human_required_prediction["p14_route"] == "human_required"
    assert human_required_prediction["final_shadow_route"] == "human_review_required"


def test_known_corpus_predictions_ignore_identifiers_hashes_paths_and_truth_pairing() -> None:
    from app.services.p146_live_shadow import predict_shadow_case, score_sealed_predictions

    corpus = build_known_conformance_corpus()
    first = corpus["visible_cases"][0]
    baseline = predict_shadow_case(first)
    assert set(baseline) == {
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
    }
    assert "case_id" not in baseline
    serialized_prediction = str(baseline).lower()
    assert first["case_id"].lower() not in serialized_prediction
    assert first["prometheus"]["source_id"].lower() not in serialized_prediction
    assert first["loki"]["source_id"].lower() not in serialized_prediction
    assert "truth" not in serialized_prediction
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
    assert report["descriptive_metrics"]["top1_accuracy"] == 1.0
    assert report["descriptive_metrics"]["top3_accuracy"] == 1.0
    assert report["descriptive_metrics"]["brier_score"] == 0.0
    assert report["descriptive_metrics"]["p95_latency_ns"] == 0
    assert set(report["wilson_intervals"]) >= {"precision", "recall", "top1_accuracy", "top3_accuracy", "citation_valid"}
    assert report["slices"]["gap"]["abstention"] == {"passed": 8, "total": 8}
    assert report["slices"]["injection"]["contained"] == {"passed": 8, "total": 8}
    assert report["slices"]["citation"]["valid"] == {"passed": 48, "total": 48}
    assert len(report["rows"]) == 48
    assert report["failure_analysis"] == []
    assert set(report["aggregate_counters"]) == {"runtime", "evaluator", "resources", "forbidden"}
    assert report["report_hash"]
    assert set(report) == {
        "schema_version",
        "corpus_version",
        "denominators",
        "confusion",
        "descriptive_metrics",
        "wilson_intervals",
        "slices",
        "failure_analysis",
        "aggregate_counters",
        "semantic_prediction_hash",
        "rows",
        "report_hash",
    }
    assert report["corpus_version"] == "p146-known-conformance-v1"
    assert report["aggregate_counters"]["evaluator"]["truth_read_count"] == 48
    assert report["aggregate_counters"]["evaluator"]["score_operation_count"] == 48
    from app.services.p124_judgment_quality import wilson_interval

    assert report["wilson_intervals"]["precision"] == wilson_interval(32, 32)
    expected_row_keys = {
        "schema_version",
        "case_ref_hash",
        "prediction_hash",
        "truth_row_hash",
        "diagnostic_match",
        "top3_match",
        "abstention_match",
        "citation_valid",
        "injection_contained",
        "latency_ns",
        "row_hash",
    }
    assert all(set(row) == expected_row_keys for row in report["rows"])
    assert all("truth_category" not in row and "top_category" not in row for row in report["rows"])
    replay = run_known_conformance_benchmark(build_known_conformance_corpus(), monotonic_ns=lambda: 1_000_000)
    assert replay["semantic_prediction_hash"] == report["semantic_prediction_hash"]


def test_live_shadow_prediction_is_derived_only_from_transported_response_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.p146_live_shadow as live_shadow
    from app.services.p146_live_shadow import run_live_shadow_episode

    visible_fault = build_known_conformance_corpus()["visible_cases"][0]
    baseline = run_live_shadow_episode(visible_fault)["prediction"]
    monkeypatch.setattr(live_shadow, "_episode_response_bytes", lambda _visible_case: _healthy_wire_responses())
    contradicted = run_live_shadow_episode(visible_fault)["prediction"]
    assert baseline["ranked_hypotheses"][0]["category"] == "deploy_regression"
    assert contradicted["ranked_hypotheses"][0]["category"] == "healthy"
    assert contradicted["diagnostic_disposition"] == "healthy"


def test_closed_counters_reconcile_and_forbidden_authority_is_zero() -> None:
    import app.services.p146_live_shadow as live_shadow
    from app.services.p146_live_shadow import run_live_shadow_episode, validate_counter_maps

    episode = run_live_shadow_episode(build_known_conformance_corpus()["visible_cases"][40])
    assert set(episode) == {"schema_version", "prediction", "request_receipts", "response_receipts", "aggregate_counters", "episode_hash"}
    validate_counter_maps(episode["aggregate_counters"])
    counters = episode["aggregate_counters"]
    assert tuple(counters["runtime"]) == RUNTIME_COUNTER_KEYS
    assert tuple(counters["evaluator"]) == EVALUATOR_COUNTER_KEYS
    assert tuple(counters["resources"]) == RESOURCE_COUNTER_KEYS
    assert tuple(counters["forbidden"]) == FORBIDDEN_COUNTER_KEYS
    for group in counters.values():
        assert all(type(value) is int for value in group.values())
    request_receipts = episode["request_receipts"]
    response_receipts = episode["response_receipts"]
    assert [receipt["schema_version"] for receipt in request_receipts] == ["p146.http_request_receipt.v1"] * 3
    assert [receipt["schema_version"] for receipt in response_receipts] == ["p146.http_response_receipt.v1"] * 3
    assert all(
        set(receipt)
        == {
            "schema_version",
            "provider",
            "capability_hash",
            "method",
            "request_target",
            "request_bytes",
            "request_sha256",
            "attempt_ordinal",
            "receipt_hash",
        }
        for receipt in request_receipts
    )
    assert all(
        set(receipt)
        == {
            "schema_version",
            "provider",
            "request_receipt_hash",
            "status_code",
            "content_type",
            "declared_bytes",
            "observed_bytes",
            "raw_sha256",
            "record_count",
            "complete",
            "failure_class",
            "receipt_hash",
        }
        for receipt in response_receipts
    )
    assert counters["runtime"]["loopback_socket_attempt_count"] == len(request_receipts)
    assert counters["runtime"]["request_commit_count"] == len(request_receipts)
    assert counters["runtime"]["request_byte_count"] == sum(receipt["request_bytes"] for receipt in request_receipts)
    assert counters["runtime"]["complete_response_count"] == sum(1 for receipt in response_receipts if receipt["complete"] is True)
    assert counters["runtime"]["response_byte_count"] == sum(receipt["observed_bytes"] for receipt in response_receipts if receipt["complete"] is True)
    assert counters["runtime"]["provider_record_count"] == sum(receipt["record_count"] for receipt in response_receipts if receipt["complete"] is True)
    assert counters["evaluator"]["accepted_connection_count"] == len(request_receipts)
    assert counters["evaluator"]["server_response_count"] == sum(1 for receipt in response_receipts if receipt["complete"] is True)
    assert counters["evaluator"]["server_response_byte_count"] == counters["runtime"]["response_byte_count"]
    assert counters["forbidden"] == {key: 0 for key in FORBIDDEN_COUNTER_KEYS}
    assert not any(Path(".").glob("evals/p146/output/*"))

    def disabled_socket(*_args: object, **_kwargs: object) -> socket.socket:
        raise AssertionError("loopback socket was not opened")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(live_shadow.socket, "socket", disabled_socket)
    try:
        with pytest.raises(AssertionError, match="loopback socket"):
            run_live_shadow_episode(build_known_conformance_corpus()["visible_cases"][0])
    finally:
        monkeypatch.undo()
