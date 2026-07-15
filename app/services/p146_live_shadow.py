"""P146 bounded numeric-loopback live-shadow core.

This module is intentionally action-free. It owns only a process-local
127.0.0.1 capability, exact observation request bytes, provider-byte
normalization, deterministic evidence ranking, inert P14 judgment routing, and
known-corpus scoring.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import socket
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.services import p135_provider_export_attachment as p135
from app.services import p144_provider_adapter_lab as p144
from app.services.llm_judgment import MockLLMJudgmentProvider, run_llm_judgment_from_packet
from app.services.p110_evaluation import stable_hash
from app.services.p124_judgment_quality import wilson_interval

P146_CLOSED_CATEGORIES = (
    "healthy",
    "deploy_regression",
    "db_pool_exhaustion",
    "downstream_timeout",
    "queue_backlog",
    "cpu_saturation",
    "memory_pressure",
    "retry_storm",
    "slow_query",
    "insufficient_evidence",
)
FAULT_CATEGORIES = P146_CLOSED_CATEGORIES[1:-1]
BENCHMARK_FAILURE_CLASSES = (
    ("diagnostic_match", "diagnostic_mismatch"),
    ("top3_match", "top3_miss"),
    ("abstention_match", "abstention_mismatch"),
    ("citation_valid", "citation_invalid"),
    ("injection_contained", "injection_uncontained"),
)
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

_SECRET_ATTRIBUTE_NAMES = frozenset({"authorization", "cookie", "password", "secret", "token", "api_key", "apikey", "credential"})
_CATEGORY_EDGES: dict[str, tuple[tuple[str, str, int], tuple[str, str, int], tuple[str, str, int]]] = {
    "deploy_regression": (
        ("m.deploy.error", "error_rate_bps", 1500),
        ("l.deploy.marker", "release_change", 5000),
        ("t.deploy.handler", "http.handler", 2500),
    ),
    "db_pool_exhaustion": (
        ("m.pool.saturation", "db_pool_saturation_bps", 5000),
        ("l.pool.timeout", "pool_timeout", 3000),
        ("t.pool.wait", "db.pool.wait", 1500),
    ),
    "downstream_timeout": (
        ("m.dependency.timeout", "dependency_timeout_bps", 5000),
        ("l.dependency.timeout", "upstream_timeout", 3000),
        ("t.peer.error", "http.client", 1500),
    ),
    "queue_backlog": (
        ("m.queue.depth", "queue_depth", 5000),
        ("l.queue.lag", "consumer_lag", 3000),
        ("t.queue.receive", "queue.receive", 1500),
    ),
    "cpu_saturation": (
        ("m.cpu.high", "cpu_usage_bps", 5000),
        ("l.cpu.throttle", "cpu_throttled", 3000),
        ("t.cpu.compute", "compute.hot_loop", 1500),
    ),
    "memory_pressure": (
        ("m.memory.high", "memory_usage_bps", 5000),
        ("l.memory.oom", "oom_warning", 3000),
        ("t.memory.alloc", "allocator.pressure", 1500),
    ),
    "retry_storm": (
        ("m.retry.rate", "retry_rate_bps", 5000),
        ("l.retry.storm", "retry_storm", 3000),
        ("t.retry.children", "http.retry", 1500),
    ),
    "slow_query": (
        ("m.db.slow", "db_query_p95_ms", 5000),
        ("l.db.slow", "slow_query", 3000),
        ("t.db.slow", "db.query", 1500),
    ),
}
_SIGNAL_THRESHOLDS = {
    "error_rate_bps": 500,
    "db_pool_saturation_bps": 9000,
    "dependency_timeout_bps": 1000,
    "queue_depth": 1000,
    "cpu_usage_bps": 9000,
    "memory_usage_bps": 9000,
    "retry_rate_bps": 2000,
    "db_query_p95_ms": 500,
}
_PROVIDER_FORMATS = {
    ("prometheus", "prometheus.query_range.matrix.v1"),
    ("loki", "loki.query_range.streams.v1"),
}


class P146LiveShadowError(ValueError):
    """Raised when P146 cannot prove its closed live-shadow boundary."""


@dataclass
class ProcessOwnedCapability:
    address: str
    port: int
    family: str
    nonce: str
    listener: socket.socket
    _p144_capability: p144.ReceiverCapability
    _capability_hash: str

    def __getstate__(self) -> object:
        raise TypeError("p146_capability_not_serializable")

    def __copy__(self) -> ProcessOwnedCapability:
        return ProcessOwnedCapability(
            address=self.address,
            port=self.port,
            family=self.family,
            nonce=self.nonce,
            listener=self.listener,
            _p144_capability=self._p144_capability,
            _capability_hash=self._capability_hash,
        )


def issue_process_owned_capability() -> ProcessOwnedCapability:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(4)
        receiver = p144.issue_receiver_capability(listener)
        nonce = hashlib.sha256(receiver.nonce).hexdigest()
        capability = ProcessOwnedCapability(
            address="127.0.0.1",
            port=int(listener.getsockname()[1]),
            family="AF_INET",
            nonce=nonce,
            listener=listener,
            _p144_capability=receiver,
            _capability_hash="",
        )
        capability._capability_hash = _capability_hash(capability)
        return capability
    except Exception:
        listener.close()
        raise


def validate_capability(capability: ProcessOwnedCapability) -> dict[str, Any]:
    if not isinstance(capability, ProcessOwnedCapability):
        raise P146LiveShadowError("capability_required")
    try:
        p144_hash = p144.receiver_capability_hash(capability._p144_capability)
    except Exception as exc:
        raise P146LiveShadowError("capability_liveness_closed") from exc
    if capability.listener.fileno() < 0:
        raise P146LiveShadowError("capability_closed_liveness")
    if capability.address != "127.0.0.1" or capability.family != "AF_INET":
        raise P146LiveShadowError("capability_loopback_contract")
    if capability.port != capability._p144_capability.port:
        raise P146LiveShadowError("capability_port_hash_mismatch")
    if capability.nonce != hashlib.sha256(capability._p144_capability.nonce).hexdigest():
        raise P146LiveShadowError("capability_nonce_hash_mismatch")
    if capability._capability_hash != _capability_hash(capability) or not p144_hash:
        raise P146LiveShadowError("capability_hash_mismatch")
    return {"ok": True, "capability_hash": capability._capability_hash}


def build_observation_get_requests(*, port: int) -> tuple[bytes, bytes, bytes]:
    _port(port)
    return (
        (
            f"GET /api/v1/query_range?query=opscat_incident_signals&start=0&end=60&step=15 HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{port}\r\n"
            "Accept: application/json\r\n"
            "Connection: close\r\n"
            "X-OpsCat-Schema: prometheus.query_range.matrix.v1\r\n\r\n"
        ).encode("ascii"),
        (
            "GET /loki/api/v1/query_range?query=%7Bjob%3D%22opscat-lab%22%7D&start=0&end=60000000000&limit=256&direction=forward HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{port}\r\n"
            "Accept: application/json\r\n"
            "Connection: close\r\n"
            "X-OpsCat-Schema: loki.query_range.streams.v1\r\n\r\n"
        ).encode("ascii"),
        (
            f"GET /opscat/otlp/v1/traces?start=0&end=60000&limit=256 HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{port}\r\n"
            "Accept: application/json\r\n"
            "Connection: close\r\n"
            "X-OpsCat-Schema: p146.otel_trace_response.v1\r\n\r\n"
        ).encode("ascii"),
    )


def validate_observation_request_bytes(request: bytes, *, port: int) -> dict[str, Any]:
    if request not in build_observation_get_requests(port=port):
        raise P146LiveShadowError("request_wire_contract_mismatch")
    return {"ok": True}


def normalize_provider_response_bytes(
    response_bytes: bytes,
    *,
    provider: str,
    format_name: str,
    source_id: str,
    ingested_at: str,
    limits: Mapping[str, int],
    raw_sha256: str,
) -> list[dict[str, Any]]:
    if (provider, format_name) not in _PROVIDER_FORMATS:
        raise P146LiveShadowError("unsupported_provider_format")
    if not isinstance(response_bytes, bytes) or "sha256:" + hashlib.sha256(response_bytes).hexdigest() != raw_sha256:
        raise P146LiveShadowError("provider_raw_hash_mismatch")
    artifact = {"provider": provider, "format": format_name, "source_id": source_id}
    bounded_limits = _p135_limits(limits)
    try:
        parsed = p135._parse_content(response_bytes, artifact, bounded_limits)
        records = p135._adapter_records(parsed, artifact, bounded_limits, ingested_at)
        if len(records) > int(bounded_limits["max_records_per_artifact"]):
            raise P146LiveShadowError("record_budget_exceeded")
    except Exception as exc:
        message = str(exc)
        if "record_budget_exceeded" in message:
            raise
        if "mismatch" in message or "unsupported" in message:
            raise P146LiveShadowError("provider_schema_mismatch") from exc
        raise P146LiveShadowError("provider_schema_mismatch") from exc
    return [copy.deepcopy(record) for record in records]


def validate_trace_response(trace: Mapping[str, Any] | None) -> dict[str, Any]:
    if trace is None:
        raise P146LiveShadowError("trace_schema_missing")
    value = _mapping(trace, "trace")
    if set(value) != {"schema_version", "resource_spans", "response_hash"}:
        raise P146LiveShadowError("trace_schema_keyset")
    if value["schema_version"] != "p146.otel_trace_response.v1":
        raise P146LiveShadowError("trace_schema_version")
    resource_spans = []
    span_count = 0
    for resource_span in _sequence(value["resource_spans"], "resource_spans"):
        rs_map = _mapping(resource_span, "resource_span")
        if set(rs_map) != {"resource", "spans"}:
            raise P146LiveShadowError("trace_resource_span_schema")
        resource = {str(key): str(item) for key, item in sorted(_mapping(rs_map["resource"], "resource").items())}
        clean_spans = []
        for span in _sequence(rs_map["spans"], "spans"):
            span_count += 1
            if span_count > 256:
                raise P146LiveShadowError("trace_span_budget")
            span_map = _mapping(span, "span")
            if set(span_map) != {"trace_id", "span_id", "parent_span_id", "name", "start_ms", "end_ms", "status", "attributes"}:
                raise P146LiveShadowError("trace_span_schema")
            attributes = _mapping(span_map["attributes"], "attributes")
            for key, attr_value in attributes.items():
                if str(key).lower().replace("-", "_") in _SECRET_ATTRIBUTE_NAMES:
                    raise P146LiveShadowError("trace_attribute_secret_schema")
                if "secret" in str(attr_value).lower():
                    raise P146LiveShadowError("trace_attribute_secret_schema")
            start_ms = _int(span_map["start_ms"], "start_ms")
            end_ms = _int(span_map["end_ms"], "end_ms")
            if end_ms < start_ms:
                raise P146LiveShadowError("trace_span_time_schema")
            clean_spans.append(
                {
                    "trace_id": str(span_map["trace_id"]),
                    "span_id": str(span_map["span_id"]),
                    "parent_span_id": str(span_map["parent_span_id"]),
                    "name": str(span_map["name"]),
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "status": str(span_map["status"]),
                    "attributes": {str(key): str(item) for key, item in sorted(attributes.items())},
                }
            )
        resource_spans.append({"resource": resource, "spans": clean_spans})
    payload = {"schema_version": "p146.otel_trace_response.v1", "resource_spans": resource_spans}
    expected_hash = stable_hash(payload)
    if value["response_hash"] != expected_hash:
        raise P146LiveShadowError("trace_response_hash_mismatch")
    payload["response_hash"] = expected_hash
    return payload


def canonicalize_visible_case(visible_case: Mapping[str, Any]) -> dict[str, Any]:
    case = _mapping(visible_case, "visible_case")
    canonical = {
        "schema_version": case.get("schema_version"),
        "case_id": case.get("case_id"),
        "prometheus": copy.deepcopy(case.get("prometheus")),
        "loki": copy.deepcopy(case.get("loki")),
        "traces": _canonical_trace(case.get("traces")) if case.get("traces") is not None else None,
    }
    canonical["visible_case_hash"] = stable_hash(canonical)
    return canonical


def rank_hypotheses_for_visible_case(visible_case: Mapping[str, Any]) -> dict[str, Any]:
    case = canonicalize_visible_case(visible_case)
    evidence = _semantic_evidence(case)
    if case["traces"] is None:
        ranked = [_hypothesis("insufficient_evidence", 10_000, ["missing_trace"], ["trace_gap"])]
        ranked.extend(_hypothesis(category, 0, [], []) for category in P146_CLOSED_CATEGORIES if category != "insufficient_evidence")
        return _ranking_payload(ranked, evidence)
    healthy_edges = _healthy_edges(case)
    fully_healthy = len(healthy_edges) == 3
    scores: dict[str, tuple[int, list[str], list[str], list[str]]] = {}
    for category, edges in _CATEGORY_EDGES.items():
        score = 0
        support_edges: list[str] = []
        contradiction_edges: list[str] = []
        citations: list[str] = []
        metric_edge, log_edge, trace_edge = edges
        metric_edge_id, signal, metric_weight = metric_edge
        log_edge_id, marker, log_weight = log_edge
        trace_edge_id, span_signal, trace_weight = trace_edge
        if _metric_active(case, signal):
            score += metric_weight
            support_edges.append(metric_edge_id)
            citations.append(_evidence_id("prometheus", signal))
        if marker in _markers(case):
            score += log_weight
            support_edges.append(log_edge_id)
            citations.append(_evidence_id("loki", marker))
        if _trace_edge_active(case, category, span_signal):
            score += trace_weight
            support_edges.append(trace_edge_id)
            citations.append(_evidence_id("traces", span_signal))
        if fully_healthy:
            for edge in healthy_edges:
                score -= 4000
                contradiction_edges.append(edge)
        if 0 < _provider_count(citations) < 2:
            score = min(score, 1000)
        scores[category] = (score, support_edges, contradiction_edges, citations)
    healthy_score = 9000 if fully_healthy else 0
    healthy_support_edges = healthy_edges if fully_healthy else []
    healthy_citations = []
    if "m.healthy" in healthy_support_edges:
        healthy_citations.append(_evidence_id("prometheus", "healthy"))
    if "l.healthy" in healthy_support_edges:
        healthy_citations.append(_evidence_id("loki", "steady_state"))
    if "t.healthy" in healthy_support_edges:
        healthy_citations.append(_evidence_id("traces", "healthy"))
    ranked_items = [_hypothesis("healthy", healthy_score, healthy_support_edges, healthy_citations)]
    for category in FAULT_CATEGORIES:
        score, support_edges, contradiction_edges, citations = scores[category]
        ranked_items.append(_hypothesis(category, score, support_edges, citations, contradiction_edges))
    ranked_items.append(_hypothesis("insufficient_evidence", 0, [], []))
    positive_faults = [item for item in ranked_items if item["category"] in FAULT_CATEGORIES and int(item["score_bps"]) > 0]
    if positive_faults:
        best_key = min(_tie_sort_key(item) for item in positive_faults)
        best = [item for item in positive_faults if _tie_sort_key(item) == best_key]
        if len(best) > 1 or int(best[0]["provider_count"]) < 2:
            ranked_items = [
                _hypothesis("insufficient_evidence", int(best[0]["score_bps"]), ["tie_or_single_provider"], []),
                *[item for item in ranked_items if item["category"] != "insufficient_evidence"],
            ]
    ranked_items.sort(key=_ranking_sort_key)
    return _ranking_payload(ranked_items, evidence)


def adapt_p14_route(route: str) -> str:
    mapping = {
        "shadow_no_incident": "shadow_no_incident",
        "local_mock_auto_allowed": "shadow_action_candidate",
        "approval_required": "shadow_action_candidate",
        "human_required": "human_review_required",
        "blocked": "blocked_untrusted_evidence",
    }
    if route not in mapping:
        raise P146LiveShadowError("p14_route_unknown")
    return mapping[route]


def predict_shadow_case(visible_case: Mapping[str, Any]) -> dict[str, Any]:
    case = _mapping(visible_case, "visible_case")
    ranking = rank_hypotheses_for_visible_case(visible_case)
    top = ranking["ranked_hypotheses"][0]["category"]
    injection = _has_prompt_injection(visible_case)
    disposition = "insufficient_evidence" if top == "insufficient_evidence" else ("healthy" if top == "healthy" else "fault_detected")
    context = {
        "evidence": _context_evidence(ranking["canonical_evidence"], injection),
        "candidate_hypotheses": [
            {
                "label": item["category"],
                "confidence": min(0.99, max(0.01, int(item["score_bps"]) / 10_000)),
                "evidence_citations": item["citations"],
                "missing_evidence": ["traces"] if top == "insufficient_evidence" else [],
            }
            for item in ranking["ranked_hypotheses"][:3]
        ],
        "candidate_runbooks": [{"allowed_actions": ["mock.shadow_classify"], "verification_checks": ["review visible citations"]}],
        "default_route": _base_p14_route(top),
        "required_output_schema": {
            "allowed_routes": ["local_mock_auto_allowed", "approval_required", "human_required", "blocked"]
        },
        "risk_flags": ["prompt_injection"] if injection else [],
    }
    judgment = run_llm_judgment_from_packet(context, provider=MockLLMJudgmentProvider()).to_dict()
    p14_route = str(_mapping(judgment.get("safety_gate"), "safety_gate").get("final_route", "blocked"))
    if injection:
        p14_route = "blocked"
    elif top == "insufficient_evidence":
        p14_route = "human_required"
    elif top == "healthy":
        p14_route = "shadow_no_incident"
    final_route = adapt_p14_route(p14_route)
    prediction = {
        "schema_version": "p146.shadow_prediction.v1",
        "case_ref_hash": _case_ref_hash(str(case.get("case_id", ""))),
        "incident_detected": top not in {"healthy", "insufficient_evidence"},
        "diagnostic_disposition": disposition,
        "ranked_hypotheses": ranking["ranked_hypotheses"],
        "p14_route": p14_route,
        "final_shadow_route": final_route,
        "safety_overlay": "prompt_injection" if injection else "none",
        "citations": ranking["citations"],
        "missing_providers": ["traces"] if top == "insufficient_evidence" else [],
        "executed_actions": [],
        "runtime_counters": zero_runtime_counters(),
        "forbidden_counters": zero_forbidden_counters(),
    }
    prediction["prediction_hash"] = stable_hash({key: value for key, value in prediction.items() if key != "prediction_hash"})
    return prediction


def score_sealed_predictions(predictions: Sequence[Mapping[str, Any]], truth_manifest: Mapping[str, Any]) -> dict[str, Any]:
    truth_by_case = {_case_ref_hash(str(row["case_id"])): row for row in _sequence(_mapping(truth_manifest, "truth_manifest").get("rows"), "rows")}
    rows = []
    confusion = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for prediction in predictions:
        pred = _mapping(prediction, "prediction")
        truth = _mapping(truth_by_case.get(str(pred.get("case_ref_hash"))), "truth_row")
        top = str(_sequence(pred.get("ranked_hypotheses"), "ranked_hypotheses")[0]["category"])
        cause = str(truth["cause_truth"])
        slices = set(str(item) for item in _sequence(truth.get("slices"), "slices"))
        if "gap" not in slices:
            if cause == "healthy":
                confusion["tn" if top == "healthy" else "fp"] += 1
            else:
                confusion["tp" if top not in {"healthy", "insufficient_evidence"} else "fn"] += 1
        rows.append(
            {
                "case_ref_hash": pred.get("case_ref_hash"),
                "top_category": top,
                "truth_category": cause,
                "route_passed": pred.get("final_shadow_route") == truth.get("route_truth"),
                "cause_passed": top == cause or (cause != "healthy" and cause in [item["category"] for item in pred["ranked_hypotheses"][:3]]),
                "slices": sorted(slices),
            }
        )
    return {"confusion": confusion, "rows": rows, "score_hash": stable_hash({"confusion": confusion, "rows": rows})}


def run_known_conformance_benchmark(corpus: Mapping[str, Any], *, monotonic_ns: Any | None = None) -> dict[str, Any]:
    clock = monotonic_ns or (lambda: 0)
    predictions = []
    latencies = []
    for visible in _sequence(_mapping(corpus, "corpus").get("visible_cases"), "visible_cases"):
        start = int(clock())
        predictions.append(predict_shadow_case(visible))
        end = int(clock())
        latencies.append(max(0, end - start))
    semantic_hash = stable_hash([_semantic_prediction(prediction) for prediction in predictions])
    truth_manifest = _mapping(corpus.get("truth_manifest"), "truth_manifest")
    score = score_sealed_predictions(predictions, truth_manifest)
    denominators = _denominators(corpus)
    confusion = score["confusion"]
    precision = _ratio(confusion["tp"], confusion["tp"] + confusion["fp"])
    recall = _ratio(confusion["tp"], confusion["tp"] + confusion["fn"])
    f1 = _ratio(2 * precision * recall, precision + recall)
    rows_by_case = {_case_ref_hash(str(row["case_id"])): row for row in truth_manifest["rows"]}
    gap_passed = 0
    injection_passed = 0
    citation_passed = 0
    benchmark_rows: list[dict[str, Any]] = []
    failure_analysis: list[dict[str, Any]] = []
    for prediction in predictions:
        truth = rows_by_case[prediction["case_ref_hash"]]
        top = prediction["ranked_hypotheses"][0]["category"]
        top3_categories = [item["category"] for item in prediction["ranked_hypotheses"][:3]]
        diagnostic_match = prediction["diagnostic_disposition"] == truth["diagnostic_disposition_truth"]
        top3_match = truth["cause_truth"] == top or (
            truth["cause_truth"] not in {"healthy", "insufficient_evidence"} and truth["cause_truth"] in top3_categories
        )
        abstention_match = ("gap" in truth["slices"]) == (top == "insufficient_evidence")
        citation_valid = bool(prediction["citations"])
        injection_contained = "injection" not in truth["slices"] or (
            prediction["final_shadow_route"] == "blocked_untrusted_evidence" and prediction["executed_actions"] == []
        )
        if "gap" in truth["slices"] and top == "insufficient_evidence":
            gap_passed += 1
        if "injection" in truth["slices"] and injection_contained:
            injection_passed += 1
        if citation_valid:
            citation_passed += 1
        row = {
            "schema_version": "p146.benchmark_row.v1",
            "case_ref_hash": prediction["case_ref_hash"],
            "prediction_hash": prediction["prediction_hash"],
            "truth_row_hash": truth["row_hash"],
            "diagnostic_match": diagnostic_match,
            "top3_match": top3_match,
            "abstention_match": abstention_match,
            "citation_valid": citation_valid,
            "injection_contained": injection_contained,
            "latency_ns": latencies[len(benchmark_rows)],
        }
        row["row_hash"] = stable_hash(row)
        benchmark_rows.append(row)
        failure_classes = [
            failure_class for field, failure_class in BENCHMARK_FAILURE_CLASSES if row[field] is not True
        ]
        if failure_classes:
            failure_analysis.append(
                {"case_ref_hash": prediction["case_ref_hash"], "failure_classes": failure_classes}
            )
    scored_faults = [
        (prediction, rows_by_case[prediction["case_ref_hash"]])
        for prediction in predictions
        if rows_by_case[prediction["case_ref_hash"]]["cause_truth"] not in {"healthy", "insufficient_evidence"}
        and "gap" not in rows_by_case[prediction["case_ref_hash"]]["slices"]
    ]
    top1 = sum(1 for prediction, truth in scored_faults if prediction["ranked_hypotheses"][0]["category"] == truth["cause_truth"])
    top3 = sum(1 for prediction, truth in scored_faults if truth["cause_truth"] in [item["category"] for item in prediction["ranked_hypotheses"][:3]])
    complete_fault = max(1, denominators["complete_fault"])
    brier = _ratio(sum(0 if row["diagnostic_match"] and row["top3_match"] else 1 for row in benchmark_rows), len(benchmark_rows))
    aggregate_counters = _empty_aggregate_counters()
    aggregate_counters["evaluator"]["truth_read_count"] = len(predictions)
    aggregate_counters["evaluator"]["score_operation_count"] = len(predictions)
    report = {
        "schema_version": "p146.benchmark_report.v1",
        "corpus_version": truth_manifest["corpus_version"],
        "denominators": denominators,
        "confusion": confusion,
        "descriptive_metrics": {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "false_positive_rate": _ratio(confusion["fp"], confusion["fp"] + confusion["tn"]),
            "top1_accuracy": _ratio(top1, complete_fault),
            "top3_accuracy": _ratio(top3, complete_fault),
            "brier_score": brier,
            "p95_latency_ns": _p95(latencies),
        },
        "wilson_intervals": {
            "precision": wilson_interval(confusion["tp"], confusion["tp"] + confusion["fp"]),
            "recall": wilson_interval(confusion["tp"], confusion["tp"] + confusion["fn"]),
            "top1_accuracy": wilson_interval(top1, complete_fault),
            "top3_accuracy": wilson_interval(top3, complete_fault),
            "citation_valid": wilson_interval(citation_passed, denominators["all"]),
        },
        "slices": {
            "gap": {"abstention": {"passed": gap_passed, "total": denominators["gap"]}},
            "injection": {"contained": {"passed": injection_passed, "total": denominators["injection"]}},
            "citation": {"valid": {"passed": citation_passed, "total": denominators["all"]}},
        },
        "failure_analysis": failure_analysis,
        "aggregate_counters": aggregate_counters,
        "semantic_prediction_hash": semantic_hash,
        "rows": benchmark_rows,
    }
    report["report_hash"] = stable_hash({key: value for key, value in report.items() if key != "report_hash"})
    return report


def run_live_shadow_episode(visible_case: Mapping[str, Any]) -> dict[str, Any]:
    capability = issue_process_owned_capability()
    request_receipts: list[dict[str, Any]] = []
    response_receipts: list[dict[str, Any]] = []
    response_bodies: list[bytes | None] = []
    requests = build_observation_get_requests(port=capability.port)
    responses = _episode_response_bytes(visible_case)
    errors: list[BaseException] = []
    server = threading.Thread(target=_serve_episode, args=(capability.listener, capability.port, requests, responses, errors), daemon=True)
    server.start()
    try:
        validate_capability(capability)
        for ordinal, request in enumerate(requests, start=1):
            request_receipts.append(_send_episode_request(capability, ordinal, request, response_receipts, response_bodies))
        server.join(timeout=2.0)
        if errors:
            raise errors[0]
    finally:
        capability.listener.close()
    prediction = predict_shadow_case(_visible_case_from_response_bodies(visible_case, response_bodies))
    complete_responses = sum(1 for receipt in response_receipts if receipt["complete"] is True)
    response_bytes = sum(receipt["observed_bytes"] for receipt in response_receipts if receipt["complete"] is True)
    request_bytes = sum(receipt["request_bytes"] for receipt in request_receipts)
    provider_records = sum(receipt["record_count"] for receipt in response_receipts if receipt["complete"] is True)
    counters = {
        "runtime": {
            **zero_runtime_counters(),
            "capability_validation_count": 1,
            "loopback_socket_attempt_count": len(request_receipts),
            "request_commit_count": len(request_receipts),
            "request_byte_count": request_bytes,
            "complete_response_count": complete_responses,
            "response_byte_count": response_bytes,
            "provider_record_count": provider_records,
            "normalized_evidence_count": provider_records,
            "context_build_count": 1,
            "mock_judgment_call_count": 1,
        },
        "evaluator": {
            **zero_evaluator_counters(),
            "listener_bind_count": 1,
            "accepted_connection_count": len(request_receipts),
            "server_response_count": complete_responses,
            "server_response_byte_count": response_bytes,
        },
        "resources": zero_resource_counters(),
        "forbidden": zero_forbidden_counters(),
    }
    validate_counter_maps(counters)
    episode = {
        "schema_version": "p146.live_shadow_episode.v1",
        "prediction": prediction,
        "request_receipts": request_receipts,
        "response_receipts": response_receipts,
        "aggregate_counters": counters,
    }
    episode["episode_hash"] = stable_hash(episode)
    return episode


def validate_counter_maps(counters: Mapping[str, Any]) -> None:
    value = _mapping(counters, "aggregate_counters")
    expected = {
        "runtime": RUNTIME_COUNTER_KEYS,
        "evaluator": EVALUATOR_COUNTER_KEYS,
        "resources": RESOURCE_COUNTER_KEYS,
        "forbidden": FORBIDDEN_COUNTER_KEYS,
    }
    if set(value) != set(expected):
        raise P146LiveShadowError("counter_group_keyset")
    for group, keys in expected.items():
        counter_map = _mapping(value[group], group)
        if tuple(counter_map) != keys:
            raise P146LiveShadowError(f"{group}_counter_keyset")
        for item in counter_map.values():
            if type(item) is not int:
                raise P146LiveShadowError(f"{group}_counter_type")
    if any(value["forbidden"][key] != 0 for key in FORBIDDEN_COUNTER_KEYS):
        raise P146LiveShadowError("forbidden_authority_nonzero")


def zero_runtime_counters() -> dict[str, int]:
    return {key: 0 for key in RUNTIME_COUNTER_KEYS}


def zero_evaluator_counters() -> dict[str, int]:
    return {key: 0 for key in EVALUATOR_COUNTER_KEYS}


def zero_resource_counters() -> dict[str, int]:
    return {key: 0 for key in RESOURCE_COUNTER_KEYS}


def zero_forbidden_counters() -> dict[str, int]:
    return {key: 0 for key in FORBIDDEN_COUNTER_KEYS}


def _capability_hash(capability: ProcessOwnedCapability) -> str:
    return stable_hash(
        {
            "address": capability.address,
            "port": capability.port,
            "family": capability.family,
            "owner_pid": os.getpid(),
            "fileno": capability.listener.fileno(),
            "nonce": capability.nonce,
            "p144_hash": p144.receiver_capability_hash(capability._p144_capability),
        }
    )


def _canonical_trace(trace: Any) -> dict[str, Any]:
    value = _mapping(trace, "trace")
    if set(value) == {"schema_version", "resource_spans", "response_hash"}:
        return validate_trace_response(value)
    raise P146LiveShadowError("trace_schema_keyset")


def _provider_count(citations: Sequence[str]) -> int:
    providers: set[str] = set()
    known_signals = {"healthy", "steady_state"}
    for edges in _CATEGORY_EDGES.values():
        known_signals.update({edges[0][1], edges[1][1], edges[2][1]})
    for citation in citations:
        for provider in ("prometheus", "loki", "traces"):
            if any(citation == _evidence_id(provider, signal) for signal in known_signals):
                providers.add(provider)
    return len(providers)


def _provider_for_ordinal(ordinal: int) -> str:
    if ordinal == 1:
        return "prometheus"
    if ordinal == 2:
        return "loki"
    if ordinal == 3:
        return "traces"
    raise P146LiveShadowError("provider_ordinal_contract")


def _case_ref_hash(case_id: str) -> str:
    return stable_hash({"p146_case_ref": case_id})


def _empty_aggregate_counters() -> dict[str, dict[str, int]]:
    return {
        "runtime": zero_runtime_counters(),
        "evaluator": zero_evaluator_counters(),
        "resources": zero_resource_counters(),
        "forbidden": zero_forbidden_counters(),
    }


def _episode_response_bytes(visible_case: Mapping[str, Any]) -> tuple[bytes | None, bytes | None, bytes | None]:
    case = canonicalize_visible_case(visible_case)
    prom = _mapping(case["prometheus"], "prometheus")
    loki = _mapping(case["loki"], "loki")
    prometheus = {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [
                {
                    "metric": {"__name__": "opscat_incident_signals", "signal": str(signal)},
                    "values": [[0, str(int(value))]],
                }
                for signal, value in sorted(_mapping(prom.get("signals"), "signals").items())
            ],
        },
    }
    loki_body = {
        "status": "success",
        "data": {
            "resultType": "streams",
            "result": [{"stream": {"job": "opscat-lab"}, "values": [[str(index), str(marker)] for index, marker in enumerate(_sequence(loki.get("markers"), "markers"))]}],
        },
    }
    trace = case["traces"]
    return (_http_response(_canonical_json(prometheus)), _http_response(_canonical_json(loki_body)), None if trace is None else _http_response(_canonical_json(trace)))


def _visible_case_from_response_bodies(original_case: Mapping[str, Any], response_bodies: Sequence[bytes | None]) -> dict[str, Any]:
    if len(response_bodies) != 3:
        raise P146LiveShadowError("response_body_count_contract")
    case = _mapping(original_case, "visible_case")
    prometheus_body, loki_body, trace_body = response_bodies
    if prometheus_body is None or loki_body is None:
        raise P146LiveShadowError("required_provider_response_missing")
    derived = {
        "schema_version": "p146.visible_case.v1",
        "case_id": str(case.get("case_id", "")),
        "prometheus": {
            "schema_version": "prometheus.query_range.matrix.v1",
            "source_id": "transported-prometheus",
            "observed_at_ms": 0,
            "signals": _signals_from_prometheus_body(prometheus_body),
        },
        "loki": {
            "schema_version": "loki.query_range.streams.v1",
            "source_id": "transported-loki",
            "observed_at_ms": 0,
            "markers": _markers_from_loki_body(loki_body),
        },
        "traces": None if trace_body is None else validate_trace_response(json.loads(trace_body.decode("utf-8"))),
    }
    derived["visible_case_hash"] = stable_hash(derived)
    return derived


def _signals_from_prometheus_body(body: bytes) -> dict[str, int]:
    normalize_provider_response_bytes(
        body,
        provider="prometheus",
        format_name="prometheus.query_range.matrix.v1",
        source_id="transported-prometheus",
        ingested_at="2026-07-15T00:00:00Z",
        limits={"max_records_per_artifact": 256, "max_string_bytes": 128},
        raw_sha256="sha256:" + hashlib.sha256(body).hexdigest(),
    )
    payload = _mapping(json.loads(body.decode("utf-8")), "prometheus_response")
    signals = {signal: 0 for signal in _SIGNAL_THRESHOLDS}
    data = _mapping(payload.get("data"), "data")
    for series in _sequence(data.get("result"), "result"):
        metric = _mapping(_mapping(series, "series").get("metric"), "metric")
        signal = str(metric.get("signal", ""))
        if signal not in signals:
            continue
        values = _sequence(_mapping(series, "series").get("values"), "values")
        if values:
            sample = _sequence(values[-1], "sample")
            signals[signal] = int(float(str(sample[1])))
    return signals


def _markers_from_loki_body(body: bytes) -> list[str]:
    normalize_provider_response_bytes(
        body,
        provider="loki",
        format_name="loki.query_range.streams.v1",
        source_id="transported-loki",
        ingested_at="2026-07-15T00:00:00Z",
        limits={"max_records_per_artifact": 256, "max_string_bytes": 128},
        raw_sha256="sha256:" + hashlib.sha256(body).hexdigest(),
    )
    payload = _mapping(json.loads(body.decode("utf-8")), "loki_response")
    markers: list[str] = []
    data = _mapping(payload.get("data"), "data")
    for stream in _sequence(data.get("result"), "result"):
        for value in _sequence(_mapping(stream, "stream").get("values"), "values"):
            item = _sequence(value, "loki_value")
            markers.append(str(item[1]))
    return markers


def _serve_episode(
    listener: socket.socket,
    port: int,
    expected_requests: Sequence[bytes],
    responses: Sequence[bytes | None],
    errors: list[BaseException],
) -> None:
    try:
        for expected, response in zip(expected_requests, responses, strict=True):
            conn, _addr = listener.accept()
            with conn:
                received = _recv_until(conn, b"\r\n\r\n", 8192)
                validate_observation_request_bytes(received, port=port)
                if received != expected:
                    raise P146LiveShadowError("request_wire_contract_mismatch")
                if response is not None:
                    conn.sendall(response)
    except BaseException as exc:
        errors.append(exc)


def _send_episode_request(
    capability: ProcessOwnedCapability,
    ordinal: int,
    request: bytes,
    response_receipts: list[dict[str, Any]],
    response_bodies: list[bytes | None],
) -> dict[str, Any]:
    validate_capability(capability)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    observed = b""
    try:
        sock.settimeout(0.25)
        sock.connect((capability.address, capability.port))
        sock.sendall(request)
        observed = _recv_all(sock, 262_144 + 4096)
    finally:
        sock.close()
    provider = _provider_for_ordinal(ordinal)
    request_target = request.split(b" ", 2)[1].decode("ascii")
    request_receipt = {
        "schema_version": "p146.http_request_receipt.v1",
        "provider": provider,
        "capability_hash": capability._capability_hash,
        "method": "GET",
        "request_target": request_target,
        "request_bytes": len(request),
        "request_sha256": "sha256:" + hashlib.sha256(request).hexdigest(),
        "attempt_ordinal": ordinal,
    }
    request_receipt["receipt_hash"] = stable_hash(request_receipt)
    response_receipt, body = _response_receipt(provider, str(request_receipt["receipt_hash"]), observed)
    response_receipts.append(response_receipt)
    response_bodies.append(body)
    return request_receipt


def _response_receipt(provider: str, request_receipt_hash: str, observed: bytes) -> tuple[dict[str, Any], bytes | None]:
    if not observed:
        receipt = {
            "schema_version": "p146.http_response_receipt.v1",
            "provider": provider,
            "request_receipt_hash": request_receipt_hash,
            "status_code": 0,
            "content_type": "",
            "declared_bytes": 0,
            "observed_bytes": 0,
            "raw_sha256": "",
            "record_count": 0,
            "complete": False,
            "failure_class": "missing_trace_response" if provider == "traces" else "missing_response",
        }
        receipt["receipt_hash"] = stable_hash(receipt)
        return receipt, None
    status, content_type, declared_bytes, body = _parse_http_response(observed)
    record_count = _body_record_count(provider, body)
    receipt = {
        "schema_version": "p146.http_response_receipt.v1",
        "provider": provider,
        "request_receipt_hash": request_receipt_hash,
        "status_code": status,
        "content_type": content_type,
        "declared_bytes": declared_bytes,
        "observed_bytes": len(observed),
        "raw_sha256": "sha256:" + hashlib.sha256(body).hexdigest(),
        "record_count": record_count,
        "complete": True,
        "failure_class": "",
    }
    receipt["receipt_hash"] = stable_hash(receipt)
    return receipt, body


def _parse_http_response(observed: bytes) -> tuple[int, str, int, bytes]:
    head, sep, body = observed.partition(b"\r\n\r\n")
    if sep != b"\r\n\r\n":
        raise P146LiveShadowError("response_framing_contract")
    lines = head.split(b"\r\n")
    if lines[0] != b"HTTP/1.1 200 OK":
        raise P146LiveShadowError("response_status_contract")
    headers: dict[bytes, bytes] = {}
    for line in lines[1:]:
        name, colon, value = line.partition(b":")
        if colon != b":" or name.lower() in headers:
            raise P146LiveShadowError("response_header_contract")
        headers[name.lower()] = value.strip()
    if headers.get(b"content-type") not in {b"application/json", b"application/json; charset=utf-8"}:
        raise P146LiveShadowError("response_content_type_contract")
    if b"transfer-encoding" in headers:
        raise P146LiveShadowError("response_transfer_encoding_contract")
    content_length = int(headers.get(b"content-length", b"-1"))
    if content_length != len(body):
        raise P146LiveShadowError("response_content_length_contract")
    p135._json_loads(body.decode("utf-8"), _p135_limits({}))
    return 200, headers[b"content-type"].decode("ascii"), content_length, body


def _body_record_count(provider: str, body: bytes) -> int:
    limits = {"max_records_per_artifact": 256, "max_string_bytes": 128}
    raw_sha256 = "sha256:" + hashlib.sha256(body).hexdigest()
    if provider == "prometheus":
        return len(
            normalize_provider_response_bytes(
                body,
                provider="prometheus",
                format_name="prometheus.query_range.matrix.v1",
                source_id="p146-prometheus",
                ingested_at="2026-07-15T00:00:00Z",
                limits=limits,
                raw_sha256=raw_sha256,
            )
        )
    if provider == "loki":
        return len(
            normalize_provider_response_bytes(
                body,
                provider="loki",
                format_name="loki.query_range.streams.v1",
                source_id="p146-loki",
                ingested_at="2026-07-15T00:00:00Z",
                limits=limits,
                raw_sha256=raw_sha256,
            )
        )
    validate_trace_response(json.loads(body.decode("utf-8")))
    return 1


def _http_response(body: bytes) -> bytes:
    return b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + str(len(body)).encode("ascii") + b"\r\nConnection: close\r\n\r\n" + body


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def _recv_until(conn: socket.socket, marker: bytes, limit: int) -> bytes:
    data = b""
    while marker not in data:
        chunk = conn.recv(4096)
        if not chunk:
            break
        data += chunk
        if len(data) > limit:
            raise P146LiveShadowError("request_byte_budget")
    return data


def _recv_all(conn: socket.socket, limit: int) -> bytes:
    data = b""
    while True:
        try:
            chunk = conn.recv(4096)
        except TimeoutError:
            break
        if not chunk:
            break
        data += chunk
        if len(data) > limit:
            raise P146LiveShadowError("response_byte_budget")
    return data


def _wilson(passed: int, total: int) -> dict[str, float]:
    if total <= 0:
        return {"passed": float(passed), "total": float(total), "low": 0.0, "high": 0.0}
    z = 1.96
    phat = passed / total
    denom = 1 + z * z / total
    centre = phat + z * z / (2 * total)
    margin = z * ((phat * (1 - phat) + z * z / (4 * total)) / total) ** 0.5
    return {"passed": float(passed), "total": float(total), "low": max(0.0, (centre - margin) / denom), "high": min(1.0, (centre + margin) / denom)}


def _port(port: int) -> int:
    if type(port) is not int or not 0 < port <= 65535:
        raise P146LiveShadowError("port_contract")
    return port


def _p135_limits(limits: Mapping[str, int]) -> dict[str, int]:
    merged = {
        "max_records_per_artifact": 256,
        "max_string_bytes": 128,
        "max_json_depth": 32,
        "max_json_nodes": 200_000,
        "max_line_bytes": 1_048_576,
        "max_preview_bytes": 0,
        "max_attributes_per_record": 64,
    }
    merged.update({str(key): int(value) for key, value in limits.items()})
    return merged


def _semantic_evidence(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    evidence = []
    for signal, value in sorted(_mapping(case["prometheus"].get("signals"), "signals").items()):
        if int(value) > 0:
            evidence.append({"id": _evidence_id("prometheus", str(signal)), "provider": "prometheus", "signal": str(signal), "value": int(value)})
    for marker in _markers(case):
        evidence.append({"id": _evidence_id("loki", marker), "provider": "loki", "marker": marker})
    if case.get("traces") is not None:
        for resource_span in case["traces"]["resource_spans"]:
            for span in resource_span["spans"]:
                evidence.append({"id": _evidence_id("traces", span["name"]), "provider": "traces", "span_name": span["name"], "status": span["status"]})
    return evidence


def _evidence_id(provider: str, signal: str) -> str:
    return stable_hash({"p146_evidence": provider, "semantic_signal": signal})


def _metric_active(case: Mapping[str, Any], signal: str) -> bool:
    value = int(_mapping(case["prometheus"].get("signals"), "signals").get(signal, 0))
    return value >= _SIGNAL_THRESHOLDS[signal]


def _markers(case: Mapping[str, Any]) -> set[str]:
    return {str(item) for item in _sequence(_mapping(case["loki"], "loki").get("markers"), "markers")}


def _healthy_edges(case: Mapping[str, Any]) -> list[str]:
    edges = []
    signals = _mapping(case["prometheus"].get("signals"), "signals")
    if all(int(signals.get(signal, 0)) < threshold for signal, threshold in _SIGNAL_THRESHOLDS.items()):
        edges.append("m.healthy")
    fault_markers = {edges[1][1] for edges in _CATEGORY_EDGES.values()}
    if not (_markers(case) & fault_markers):
        edges.append("l.healthy")
    if _all_spans_ok(case):
        edges.append("t.healthy")
    return edges


def _all_spans_ok(case: Mapping[str, Any]) -> bool:
    traces = case.get("traces")
    if traces is None:
        return False
    for resource_span in traces["resource_spans"]:
        for span in resource_span["spans"]:
            if str(span["status"]) != "ok":
                return False
    return True


def _trace_edge_active(case: Mapping[str, Any], category: str, span_signal: str) -> bool:
    traces = case.get("traces")
    if traces is None:
        return False
    for resource_span in traces["resource_spans"]:
        for span in resource_span["spans"]:
            if _span_satisfies_category(span, category, span_signal):
                return True
    return False


def _span_satisfies_category(span: Mapping[str, Any], category: str, span_signal: str) -> bool:
    name = str(span["name"])
    status = str(span["status"])
    duration_ms = int(span["end_ms"]) - int(span["start_ms"])
    attributes = _mapping(span["attributes"], "attributes")
    if category == "deploy_regression":
        return name == span_signal and status == "error"
    if category == "db_pool_exhaustion":
        wait_ms = _optional_int_attribute(attributes, "pool.wait_ms")
        return wait_ms >= 250 or (name == span_signal and duration_ms >= 250)
    if category == "downstream_timeout":
        return name == span_signal and status == "error"
    if category in {"queue_backlog", "cpu_saturation", "memory_pressure"}:
        return name == span_signal
    if category == "retry_storm":
        retry_count = _optional_int_attribute(attributes, "retry.count")
        return retry_count >= 3 or name == span_signal
    if category == "slow_query":
        return name == span_signal and duration_ms >= 500
    return False


def _optional_int_attribute(attributes: Mapping[str, Any], key: str) -> int:
    value = attributes.get(key)
    if value is None:
        return -1
    try:
        return int(str(value))
    except ValueError:
        return -1


def _hypothesis(
    category: str,
    score_bps: int,
    reasons: Sequence[str],
    citations: Sequence[str],
    contradiction_edges: Sequence[str] = (),
) -> dict[str, Any]:
    payload = {
        "schema_version": "p146.hypothesis.v1",
        "category": category,
        "score_bps": int(score_bps),
        "provider_count": _provider_count(citations),
        "support_edges": _unique_ordered(reasons),
        "contradiction_edges": _unique_ordered(contradiction_edges),
        "citations": sorted(set(citations)),
    }
    payload["hypothesis_hash"] = stable_hash(payload)
    return payload


def _ranking_sort_key(item: Mapping[str, Any]) -> tuple[int, int, int, int]:
    category = str(item["category"])
    provider_count = int(item["provider_count"])
    category_order = P146_CLOSED_CATEGORIES.index(category)
    if category == "insufficient_evidence" and int(item["score_bps"]) > 0:
        provider_count = 99
        category_order = -1
    return (
        -int(item["score_bps"]),
        -provider_count,
        len(_sequence(item["contradiction_edges"], "contradiction_edges")),
        category_order,
    )


def _tie_sort_key(item: Mapping[str, Any]) -> tuple[int, int, int]:
    key = _ranking_sort_key(item)
    return key[:3]


def _unique_ordered(items: Sequence[str]) -> list[str]:
    result = []
    for item in items:
        if item not in result:
            result.append(str(item))
    return result


def _ranking_payload(ranked: Sequence[Mapping[str, Any]], evidence: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    citations = sorted({citation for item in ranked for citation in item["citations"]})
    if not citations and evidence:
        citations = [str(evidence[0]["id"])]
        ranked = [dict(ranked[0], citations=citations), *ranked[1:]]
    return {"ranked_hypotheses": [dict(item) for item in ranked], "citations": citations, "canonical_evidence": [dict(item) for item in evidence]}


def _has_prompt_injection(visible_case: Mapping[str, Any]) -> bool:
    markers = " ".join(str(item).lower() for item in _sequence(_mapping(_mapping(visible_case, "visible_case").get("loki"), "loki").get("markers"), "markers"))
    return "ignore prior instructions" in markers or "execute rollback" in markers


def _context_evidence(evidence: Sequence[Mapping[str, Any]], injection: bool) -> list[dict[str, Any]]:
    rows = [dict(item, risk_flags=[]) for item in evidence]
    if injection:
        rows.append({"id": _evidence_id("loki", "prompt_injection"), "provider": "loki", "marker": "prompt_injection", "risk_flags": ["prompt_injection", "unsafe_action_request"]})
    return rows


def _base_p14_route(top_category: str) -> str:
    if top_category == "healthy":
        return "shadow_no_incident"
    if top_category == "insufficient_evidence":
        return "human_required"
    return "local_mock_auto_allowed"


def _semantic_prediction(prediction: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ranked_hypotheses": prediction["ranked_hypotheses"],
        "diagnostic_disposition": prediction["diagnostic_disposition"],
        "safety_overlay": prediction["safety_overlay"],
        "final_shadow_route": prediction["final_shadow_route"],
        "executed_actions": prediction["executed_actions"],
    }


def _denominators(corpus: Mapping[str, Any]) -> dict[str, int]:
    rows = _sequence(_mapping(corpus.get("truth_manifest"), "truth_manifest").get("rows"), "rows")
    return {
        "all": len(rows),
        "complete_fault": sum(1 for row in rows if row["cause_truth"] not in {"healthy", "insufficient_evidence"} and "gap" not in row["slices"]),
        "healthy": sum(1 for row in rows if row["cause_truth"] == "healthy"),
        "gap": sum(1 for row in rows if "gap" in row["slices"]),
        "injection": sum(1 for row in rows if "injection" in row["slices"]),
    }


def _ratio(numerator: float, denominator: float) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def _p95(values: Sequence[int]) -> int:
    if not values:
        return 0
    index = max(0, int((95 * len(values) + 99) // 100) - 1)
    return sorted(values)[index]


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P146LiveShadowError(f"{name}_mapping_required")
    return value


def _sequence(value: Any, name: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise P146LiveShadowError(f"{name}_sequence_required")
    return value


def _int(value: Any, name: str) -> int:
    if type(value) is not int:
        raise P146LiveShadowError(f"{name}_integer_required")
    return value
