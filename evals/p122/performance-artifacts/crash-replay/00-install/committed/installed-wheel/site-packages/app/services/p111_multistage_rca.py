"""P111 deterministic multistage RCA evidence digest.

P111 is an additive layer over sealed P110 candidate packets. It builds a
candidate-visible diagnostic digest and prompt envelope without changing any
P110 packet fields or invoking a provider.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from app.services.p110_candidate_runner import (
    P110CandidateProvider,
    P110RunnerConfig,
    build_p110_candidate_packet,
    replay_p110_raw_response,
    run_p110_candidate_diagnostics,
)
from app.services.p111_fault_prior import score_fault_priors, validate_fault_prior

P111_PACKET_SCHEMA_VERSION = "p111.multistage_rca_packet.v1"
P111_DIGEST_SCHEMA_VERSION = "p111.evidence_digest.v1"
P111_PROMPT_SCHEMA_VERSION = "p111.localization_prompt.v1"
P111_DIGEST_ALGORITHM_VERSION = "p111.digest.robust-relative.v1"
P111_OUTPUT_CONTRACT_VERSION = "p110.candidate_output_keys.v1"
P111_PROMPT_HASH_VERSION = "p111.prompt_hash.v1"
P111_SYSTEM_PROMPT = "You are an evidence-driven incident RCA candidate. Compare and refute all allowed hypotheses, then return one strict JSON object only. Never execute actions."

P110_OUTPUT_KEYS = ("case_id", "ranked_services", "fault_type", "evidence_refs", "confidence", "abstain", "advisory_actions")
FAULT_ALLOWLIST = ("cpu", "mem", "disk", "delay", "loss")
_WINDOW_ORDER = ("pre", "post", "delta")
_FORBIDDEN_KEY_MARKERS = (
    "scorer_only",
    "truth",
    "root_service",
    "source_path",
    "case_directory",
    "repetition",
    "case_path",
    "truth_hash",
)
_FORBIDDEN_VALUE_MARKERS = (
    "scorer_only_truth",
    "truth.json",
    "root_service",
    "source_path",
    "case_directory",
    "repetition",
)
_SOURCE_PATH_PATTERN = re.compile(r"\b[a-z][a-z0-9-]+_(?:cpu|mem|disk|delay|loss)/[1-5]\b")


class P111MultistageRCAError(ValueError):
    """Raised when a sealed P110 packet is not safe for P111 candidate use."""


def build_p111_packet(
    p110_sealed_packet: Mapping[str, Any], *, fault_prior_artifact: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Embed an unchanged sealed P110 packet with a deterministic digest."""
    sealed_packet = _stable(p110_sealed_packet)
    if not isinstance(sealed_packet, Mapping):
        raise P111MultistageRCAError("p110_packet_not_object")
    _reject_truth_leak(sealed_packet)
    digest = build_evidence_digest(sealed_packet)
    fault_prior_scores = None
    if fault_prior_artifact is not None:
        validate_fault_prior(fault_prior_artifact)
        fault_prior_scores = score_fault_priors(digest, _service_allowlist(sealed_packet), fault_prior_artifact)
    prompt = build_p111_prompt(sealed_packet, digest, fault_prior_scores=fault_prior_scores)
    packet: dict[str, Any] = {
        "schema_version": P111_PACKET_SCHEMA_VERSION,
        "digest_schema_version": P111_DIGEST_SCHEMA_VERSION,
        "prompt_schema_version": P111_PROMPT_SCHEMA_VERSION,
        "algorithm_version": P111_DIGEST_ALGORITHM_VERSION,
        "case_id": str(sealed_packet.get("case_id", "")),
        "service_allowlist": _service_allowlist(sealed_packet),
        "fault_allowlist": list(FAULT_ALLOWLIST),
        "evidence_ids": list(digest["evidence_ids"]),
        "p110_packet": sealed_packet,
        "evidence_digest": digest,
        "hashes": {
            "p110_packet_hash": stable_hash(sealed_packet),
            "evidence_digest_hash": stable_hash(digest),
            "prompt_hash": stable_hash({"hash_version": P111_PROMPT_HASH_VERSION, "prompt": prompt}),
        },
    }
    if fault_prior_scores is not None:
        packet["fault_prior_scores"] = fault_prior_scores
    packet["packet_hash"] = stable_hash({key: value for key, value in packet.items() if key != "packet_hash"})
    return packet


def build_evidence_digest(p110_sealed_packet: Mapping[str, Any]) -> dict[str, Any]:
    """Build per service/metric pre/post/delta rows from P110 visible evidence."""
    _reject_truth_leak(p110_sealed_packet)
    evidence = _evidence_rows(p110_sealed_packet)
    grouped: dict[tuple[str, str], dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in evidence:
        service = str(row.get("service", ""))
        metric = str(row.get("metric", ""))
        window = str(row.get("window", ""))
        evidence_id = _evidence_id(row)
        if service and metric and window in _WINDOW_ORDER and evidence_id:
            grouped[(service, metric)][window] = row

    entries: list[dict[str, Any]] = []
    for service, metric in sorted(grouped):
        windows = grouped[(service, metric)]
        pre = _finite_number(windows.get("pre", {}).get("value"))
        post = _finite_number(windows.get("post", {}).get("value"))
        reported_delta = _finite_number(windows.get("delta", {}).get("value"))
        delta = reported_delta if "delta" in windows else _round(post - pre)
        relative_change = _safe_relative_change(delta, pre)
        evidence_ids = [_evidence_id(windows[window]) for window in _WINDOW_ORDER if window in windows and _evidence_id(windows[window])]
        entries.append(
            {
                "service": service,
                "metric": metric,
                "window_statistics": {
                    window: str(windows[window].get("statistic", "value")) for window in _WINDOW_ORDER if window in windows
                },
                "pre": pre,
                "post": post,
                "delta": delta,
                "relative_change": relative_change,
                "absolute_relative_change": _round(abs(relative_change)),
                "evidence_ids": evidence_ids,
                "window_evidence_ids": {window: _evidence_id(windows[window]) for window in _WINDOW_ORDER if window in windows and _evidence_id(windows[window])},
            }
        )

    ranked = _with_magnitude_ranks(entries)
    digest: dict[str, Any] = {
        "schema_version": P111_DIGEST_SCHEMA_VERSION,
        "algorithm_version": P111_DIGEST_ALGORITHM_VERSION,
        "case_id": str(p110_sealed_packet.get("case_id", "")),
        "entry_count": len(ranked),
        "entries": ranked,
        "evidence_ids": sorted({evidence_id for entry in ranked for evidence_id in entry["evidence_ids"]}),
    }
    digest["digest_hash"] = stable_hash({key: value for key, value in digest.items() if key != "digest_hash"})
    return digest


def build_p111_prompt(
    p110_sealed_packet: Mapping[str, Any],
    evidence_digest: Mapping[str, Any] | None = None,
    *,
    fault_prior_scores: Mapping[str, Any] | None = None,
) -> str:
    """Return strict JSON prompt text; no provider orchestration is performed."""
    _reject_truth_leak(p110_sealed_packet)
    digest = _stable(evidence_digest if evidence_digest is not None else build_evidence_digest(p110_sealed_packet))
    service_allowlist = _service_allowlist(p110_sealed_packet)
    prompt = {
        "prompt_schema_version": P111_PROMPT_SCHEMA_VERSION,
        "output_contract_version": P111_OUTPUT_CONTRACT_VERSION,
        "task": "localize the most likely service explicitly and produce five fault hypotheses with refutations from candidate-visible evidence only",
        "instructions": [
            "Return one strict JSON object only.",
            f"The JSON object MUST contain exactly these keys in meaning: {', '.join(P110_OUTPUT_KEYS)}.",
            "ranked_services MUST contain at most five unique service_allowlist values, ordered most likely first.",
            "fault_type MUST be one of fault_allowlist or null when abstaining.",
            "evidence_refs MUST cite only evidence_digest.evidence_ids.",
            "Internally compare all five fault hypotheses and actively seek refuting evidence before choosing one.",
            "advisory_actions MUST contain at most three short inspection suggestions and will never be executed.",
            "Do not include labels, truth fields, raw path identifiers, run identifiers, scores, or extra keys.",
        ],
        "required_output_keys": list(P110_OUTPUT_KEYS),
        "forbidden_output_keys": ["score", "success", "passed", "result_score", "candidate_score", "candidate_submitted_score", "release_qualified"],
        "output_shape": {
            "case_id": str(p110_sealed_packet.get("case_id", "")),
            "ranked_services": [],
            "fault_type": None,
            "evidence_refs": [],
            "confidence": 0.0,
            "abstain": True,
            "advisory_actions": ["inspect the strongest cited metric without changing the system"],
        },
        "service_allowlist": service_allowlist,
        "fault_allowlist": list(FAULT_ALLOWLIST),
        "fault_hypothesis_rubric": {
            "cpu": "service-local CPU change dominates; do not infer CPU from latency alone",
            "mem": "service-local memory growth dominates and is not merely downstream load",
            "disk": "service-local latency/error/load degradation without proportional CPU or memory growth; storage pressure can be indirect",
            "delay": "latency rises while error rate and throughput loss remain comparatively limited",
            "loss": "error or throughput-loss pattern dominates, often across a dependency path; distinguish from latency-only delay",
        },
        "evidence_digest": digest,
    }
    if fault_prior_scores is not None:
        prompt["learned_fault_prior"] = _stable(fault_prior_scores)
        prompt["instructions"].append(
            "learned_fault_prior was trained only on governed earlier repetitions; use it as a prior and contradict it only with cited evidence."
        )
    return _dumps(prompt)


def run_p111_candidate_diagnostics(
    cases: Sequence[Mapping[str, Any]],
    *,
    mode: str,
    provider: P110CandidateProvider,
    config: P110RunnerConfig,
    replay_outputs: Mapping[str, Mapping[str, Any] | str] | None = None,
    fault_prior_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run P111 packets through the proven P110 validation/replay boundary."""

    if config.prompt_schema_version != P111_PROMPT_SCHEMA_VERSION:
        raise P111MultistageRCAError("p111_prompt_schema_required")
    if fault_prior_artifact is not None:
        validate_fault_prior(fault_prior_artifact)

    def packet_builder(case: Mapping[str, Any]) -> Mapping[str, Any]:
        return build_p111_packet(build_p110_candidate_packet(case), fault_prior_artifact=fault_prior_artifact)

    def prompt_builder(packet: Mapping[str, Any], _config: P110RunnerConfig) -> str:
        nested = packet.get("p110_packet")
        digest = packet.get("evidence_digest")
        if not isinstance(nested, Mapping) or not isinstance(digest, Mapping):
            raise P111MultistageRCAError("invalid_p111_packet")
        prior_scores = packet.get("fault_prior_scores")
        return build_p111_prompt(
            nested,
            digest,
            fault_prior_scores=prior_scores if isinstance(prior_scores, Mapping) else None,
        )

    report = run_p110_candidate_diagnostics(
        cases,
        mode=mode,
        provider=provider,
        replay_outputs=replay_outputs,
        config=config,
        packet_builder=packet_builder,
        prompt_builder=prompt_builder,
    )
    report["schema_version"] = "p111.multistage_rca_report.v1"
    report["provenance"]["digest_algorithm_version"] = P111_DIGEST_ALGORITHM_VERSION
    report["provenance"]["output_contract_version"] = P111_OUTPUT_CONTRACT_VERSION
    if fault_prior_artifact is not None:
        report["provenance"]["fault_prior_artifact_hash"] = fault_prior_artifact["artifact_hash"]
        report["predictions"] = [
            _synthesize_fault_prediction(prediction, config=config) for prediction in report["predictions"]
        ]
    return report


def _synthesize_fault_prediction(prediction: Mapping[str, Any], *, config: P110RunnerConfig) -> dict[str, Any]:
    if prediction.get("validation_status") != "valid" or not prediction.get("ranked_services"):
        return dict(prediction)
    packet = prediction.get("candidate_context")
    raw = prediction.get("raw_response")
    if not isinstance(packet, Mapping) or not isinstance(raw, str):
        return dict(prediction)
    scores = packet.get("fault_prior_scores")
    ranked_faults = scores.get("ranked_faults") if isinstance(scores, Mapping) else None
    ranked_services = scores.get("ranked_services") if isinstance(scores, Mapping) else None
    if not isinstance(ranked_faults, Sequence) or not ranked_faults or not isinstance(ranked_services, Sequence) or not ranked_services:
        return dict(prediction)
    try:
        provider_data = json.loads(raw)
    except json.JSONDecodeError:
        return dict(prediction)
    if not isinstance(provider_data, dict):
        return dict(prediction)
    provider_data["ranked_services"] = [str(item) for item in ranked_services[:5]]
    provider_data["fault_type"] = str(ranked_faults[0])
    synthesized_raw = _dumps(provider_data)
    synthesized = replay_p110_raw_response(packet, synthesized_raw, config=config)
    synthesized["latency_ms"] = int(prediction.get("latency_ms", 0))
    synthesized["provider_stage"] = {
        "raw_response": raw,
        "raw_response_sha256": prediction.get("raw_response_sha256"),
        "parsed_prediction": {
            field: prediction.get(field)
            for field in (
                "case_id", "ranked_services", "fault_type", "evidence_refs", "confidence", "abstain",
                "validation_status", "validation_errors", "advisory_actions", "advisory_action_risk", "executed_actions",
            )
        },
    }
    synthesized["synthesis"] = {
        "schema_version": "p111.deterministic_fault_synthesis.v1",
        "selected_service": str(ranked_services[0]),
        "selected_fault": str(ranked_faults[0]),
        "ranked_faults": [str(item) for item in ranked_faults],
        "ranked_services": [str(item) for item in ranked_services[:5]],
        "fault_prior_artifact_hash": scores.get("artifact_hash") if isinstance(scores, Mapping) else None,
        "response_origin": "deterministic_synthesis",
    }
    return synthesized


def stable_hash(value: Any) -> str:
    """Return deterministic sha256 over canonical JSON."""
    return f"sha256:{hashlib.sha256(_dumps(value).encode('utf-8')).hexdigest()}"


def _with_magnitude_ranks(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_metric: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for entry in entries:
        by_metric[str(entry["metric"])].append(entry)
    rank_by_key: dict[tuple[str, str], tuple[int, float]] = {}
    for metric, metric_entries in by_metric.items():
        ordered = sorted(metric_entries, key=lambda item: (-float(item["absolute_relative_change"]), str(item["service"])))
        count = len(ordered)
        for index, entry in enumerate(ordered, start=1):
            percentile = 1.0 if count == 1 else _round((count - index) / (count - 1))
            rank_by_key[(str(entry["service"]), metric)] = (index, percentile)
    ranked: list[dict[str, Any]] = []
    for entry in sorted(entries, key=lambda item: (str(item["service"]), str(item["metric"]))):
        normalized = dict(entry)
        rank, percentile = rank_by_key[(str(entry["service"]), str(entry["metric"]))]
        normalized["magnitude_rank"] = rank
        normalized["magnitude_percentile"] = percentile
        ranked.append(normalized)
    return ranked


def _safe_relative_change(delta: float, pre: float) -> float:
    denominator = abs(pre) if abs(pre) >= 1.0 else 1.0
    return _round(delta / denominator)


def _finite_number(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return _round(number)


def _round(value: float) -> float:
    return round(float(value), 12)


def _evidence_rows(packet: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    value = packet.get("evidence", packet.get("candidate_visible_evidence", ()))
    return tuple(item for item in _sequence(value) if isinstance(item, Mapping))


def _evidence_id(row: Mapping[str, Any]) -> str:
    return str(row.get("evidence_id", row.get("id", "")))


def _service_allowlist(packet: Mapping[str, Any]) -> list[str]:
    explicit = tuple(str(item) for item in _sequence(packet.get("service_allowlist", packet.get("service_catalog", ()))))
    services = explicit or tuple(str(row.get("service", "")) for row in _evidence_rows(packet))
    return sorted(dict.fromkeys(service for service in services if service and not _contains_truth_leak(service)))


def _reject_truth_leak(value: Any) -> None:
    if _contains_truth_leak(value):
        raise P111MultistageRCAError("candidate_visible_truth_leak")


def _contains_truth_leak(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered_key = str(key).lower()
            if any(marker in lowered_key for marker in _FORBIDDEN_KEY_MARKERS):
                return True
            if _contains_truth_leak(item):
                return True
        return False
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return any(_contains_truth_leak(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return any(marker in lowered for marker in _FORBIDDEN_VALUE_MARKERS) or bool(_SOURCE_PATH_PATTERN.search(lowered))
    return False


def _stable(value: Any) -> Any:
    return json.loads(_dumps(value))


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=True, default=str)


def _sequence(value: Any) -> tuple[Any, ...]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return tuple(value)
    return ()


__all__ = [
    "FAULT_ALLOWLIST",
    "P110_OUTPUT_KEYS",
    "P111_DIGEST_ALGORITHM_VERSION",
    "P111_DIGEST_SCHEMA_VERSION",
    "P111_OUTPUT_CONTRACT_VERSION",
    "P111_PACKET_SCHEMA_VERSION",
    "P111_PROMPT_HASH_VERSION",
    "P111_PROMPT_SCHEMA_VERSION",
    "P111_SYSTEM_PROMPT",
    "P111MultistageRCAError",
    "build_evidence_digest",
    "build_p111_packet",
    "build_p111_prompt",
    "run_p111_candidate_diagnostics",
    "stable_hash",
]
