"""P110 candidate diagnosis runner with mock/replay/explicit NVIDIA modes.

The runner accepts mapping-shaped RCAEval cases, seals a candidate-visible
packet, validates strict JSON provider output, and fails closed to abstention
on leak, schema, provider, budget, or cache violations. It never executes
advisory actions.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

SCHEMA_VERSION = "p110.candidate_runner_report.v1"
PACKET_SCHEMA_VERSION = "p110.candidate_packet.v1"
PROMPT_SCHEMA_VERSION = "p110.candidate_prompt.v1"
DEFAULT_MODEL = "mock/p110-deterministic"
DEFAULT_DECODING_CONFIG: Mapping[str, Any] = {"temperature": 0.0, "top_p": 1.0, "max_tokens": 2048}
FAULT_ALLOWLIST = ("cpu", "mem", "disk", "delay", "loss")
MAX_ADVISORY_ACTIONS = 3
MAX_ADVISORY_ACTION_CHARS = 240
_ALLOWED_OUTPUT_KEYS = frozenset({"case_id", "ranked_services", "fault_type", "evidence_refs", "confidence", "abstain", "advisory_actions"})
_FORBIDDEN_SUBMITTED_FIELDS = frozenset({"score", "success", "passed", "result_score", "candidate_score", "candidate_submitted_score", "release_qualified"})
_TRUTH_KEY_MARKERS = (
    "scorer_only",
    "truth",
    "root_service",
    "fault_type",
    "fault_family",
    "qualification",
    "release_qualifying",
    "source_path",
    "case_directory",
    "truth_hash",
)
_TRUTH_VALUE_MARKERS = ("scorer_only_truth", "root_service", "fault_type", "truth.json", "/cpu/", "/mem/", "/disk/", "/delay/", "/loss/")
_HARMFUL_ACTION_MARKERS = (
    "kubectl",
    "delete",
    "restart",
    "rm -rf",
    "drop database",
    "terraform apply",
    "aws ",
    "gcloud ",
    "scale ",
    "cordon",
    "drain",
    "kill ",
    "chmod ",
    "chown ",
    "production",
)


class P110CandidateProvider(Protocol):
    name: str
    model_calls_enabled: bool

    def diagnose(self, packet: Mapping[str, Any], prompt: str) -> Mapping[str, Any] | str: ...


@dataclass(frozen=True)
class P110RunnerConfig:
    model: str = DEFAULT_MODEL
    prompt_schema_version: str = PROMPT_SCHEMA_VERSION
    decoding_config: Mapping[str, Any] = field(default_factory=lambda: dict(DEFAULT_DECODING_CONFIG))
    max_cases: int = 25
    max_calls: int = 25
    max_prompt_chars: int = 120_000
    max_response_chars: int = 40_000
    max_retries: int = 1
    fault_allowlist: tuple[str, ...] = FAULT_ALLOWLIST


class MockP110CandidateProvider:
    name = "mock"
    model_calls_enabled = False

    def diagnose(self, packet: Mapping[str, Any], prompt: str) -> Mapping[str, Any]:
        evidence = _mapping_sequence(packet.get("evidence"))
        services = tuple(str(item) for item in _sequence(packet.get("service_allowlist")))
        return {
            "case_id": str(packet.get("case_id", "")),
            "ranked_services": list(services[:3]),
            "fault_type": "cpu",
            "evidence_refs": [str(item.get("id")) for item in evidence[:2] if item.get("id")],
            "confidence": 0.25,
            "abstain": not bool(services),
            "advisory_actions": ["inspect cited evidence"],
        }


class NvidiaP110CandidateProvider:
    """Explicit opt-in NVIDIA provider.

    Tests can inject a fake OpenAI-compatible client. Without a client, an
    NVIDIA_API_KEY is required; this class is never selected by default.
    """

    name = "nvidia"
    model_calls_enabled = True

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "nvidia/nemotron-3-ultra-550b-a55b",
        client: Any | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY")
        if client is None and not self.api_key:
            raise RuntimeError("NVIDIA_API_KEY is required for explicit P110 NVIDIA mode")
        self.model = model
        self._client = client
        self.system_prompt = system_prompt or _system_prompt()

    def diagnose(self, packet: Mapping[str, Any], prompt: str) -> Mapping[str, Any] | str:
        client = self._client or self._build_client()
        stream = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": self.system_prompt}, {"role": "user", "content": prompt}],
            temperature=1.0,
            top_p=0.95,
            max_tokens=16384,
            extra_body={"chat_template_kwargs": {"enable_thinking": True}, "reasoning_budget": 16384},
            stream=True,
        )
        parts: list[str] = []
        for chunk in stream:
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            content = getattr(delta, "content", None)
            if content is None and isinstance(choices[0], Mapping):
                raw_delta = choices[0].get("delta")
                content = raw_delta.get("content") if isinstance(raw_delta, Mapping) else None
            if isinstance(content, str):
                parts.append(content)
        combined = "".join(parts).strip()
        if not combined:
            raise ValueError("NVIDIA response contained no content")
        return combined

    def _build_client(self) -> Any:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("install the optional openai client before using P110 NVIDIA mode") from exc
        return OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=self.api_key, timeout=180.0, max_retries=0)


def run_p110_candidate_diagnostics(
    cases: Sequence[Mapping[str, Any]],
    *,
    mode: str = "mock",
    provider: P110CandidateProvider | None = None,
    replay_outputs: Mapping[str, Mapping[str, Any] | str] | None = None,
    cache: MutableMapping[str, Mapping[str, Any] | str] | None = None,
    config: P110RunnerConfig | None = None,
    packet_builder: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    prompt_builder: Callable[[Mapping[str, Any], P110RunnerConfig], str] | None = None,
) -> dict[str, Any]:
    cfg = config or P110RunnerConfig()
    selected_provider = provider or _default_provider(mode)
    predictions: list[dict[str, Any]] = []
    provider_call_count = 0
    cache_hits = 0
    cache_writes = 0

    for index, case in enumerate(cases):
        latency_ms = 0
        if index >= cfg.max_cases:
            predictions.append(_abstain_prediction(str(case.get("case_id", "")), ("budget_overrun:max_cases",), config=cfg))
            continue
        packet = dict(packet_builder(case)) if packet_builder is not None else build_p110_candidate_packet(case)
        cache_key = compute_p110_cache_key(model=cfg.model, packet=packet, prompt_schema_version=cfg.prompt_schema_version, decoding_config=cfg.decoding_config)
        packet_errors = _packet_validation_errors(packet)
        if packet_errors:
            predictions.append(_abstain_prediction(str(packet.get("case_id", "")), packet_errors, packet=packet, cache_key=cache_key, config=cfg))
            continue
        prompt = prompt_builder(packet, cfg) if prompt_builder is not None else build_p110_prompt(packet, config=cfg)
        if len(prompt) > cfg.max_prompt_chars:
            predictions.append(_abstain_prediction(str(packet.get("case_id", "")), ("budget_overrun:max_prompt_chars",), packet=packet, cache_key=cache_key, config=cfg))
            continue
        raw: Mapping[str, Any] | str
        if replay_outputs is not None:
            raw, replay_errors = _replay_raw_for_cache_key(replay_outputs, cache_key)
            if replay_errors:
                predictions.append(_abstain_prediction(str(packet.get("case_id", "")), replay_errors, packet=packet, cache_key=cache_key, config=cfg))
                continue
        elif cache is not None and cache_key in cache:
            raw = cache[cache_key]
            cache_hits += 1
        else:
            if provider_call_count >= cfg.max_calls:
                predictions.append(_abstain_prediction(str(packet.get("case_id", "")), ("budget_overrun:max_calls",), packet=packet, cache_key=cache_key, config=cfg))
                continue
            raw, calls, latency_ms = _diagnose_with_retries(selected_provider, packet, prompt, cfg, remaining_calls=cfg.max_calls - provider_call_count)
            provider_call_count += calls
            if isinstance(raw, Mapping) and raw.get("__provider_error__"):
                predictions.append(_abstain_prediction(str(packet.get("case_id", "")), (str(raw["__provider_error__"]),), packet=packet, cache_key=cache_key, config=cfg, latency_ms=latency_ms))
                continue
            if cache is not None:
                cache[cache_key] = raw
                cache_writes += 1
        response_size = _raw_size(raw)
        if response_size > cfg.max_response_chars:
            predictions.append(_abstain_prediction(str(packet.get("case_id", "")), ("budget_overrun:max_response_chars",), packet=packet, cache_key=cache_key, config=cfg, raw=raw))
            continue
        predictions.append(_prediction_from_raw(raw, packet, cfg, cache_key=cache_key, latency_ms=latency_ms))

    harmful_action_count = sum(1 for prediction in predictions for item in prediction["advisory_action_risk"] if item["risk"] == "harmful")
    truth_leak_count = sum(1 for prediction in predictions if "candidate_packet_truth_leak" in prediction["validation_errors"])
    fail_closed_count = sum(1 for prediction in predictions if prediction["validation_status"] != "valid")
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "provider": getattr(selected_provider, "name", mode),
        "model": cfg.model,
        "summary": {
            "case_count": len(cases),
            "prediction_count": len(predictions),
            "valid_count": sum(1 for prediction in predictions if prediction["validation_status"] == "valid"),
            "fail_closed_count": fail_closed_count,
            "network_calls_enabled": bool(getattr(selected_provider, "model_calls_enabled", False) and mode == "nvidia"),
            "action_execution_enabled": False,
        },
        "budget": {"max_cases": cfg.max_cases, "max_calls": cfg.max_calls, "provider_call_count": provider_call_count, "max_retries": cfg.max_retries},
        "cache": {"hit_count": cache_hits, "write_count": cache_writes},
        "provenance": {
            "model": cfg.model,
            "prompt_schema_version": cfg.prompt_schema_version,
            "decoding_config": _stable(cfg.decoding_config),
            "prediction_count": len(predictions),
            "prediction_cache_keys": [str(prediction.get("cache_key", "")) for prediction in predictions],
            "prediction_provenance": [_report_prediction_provenance(prediction) for prediction in predictions],
        },
        "safety": {"truth_leak_count": truth_leak_count, "harmful_action_count": harmful_action_count, "executed_action_count": 0},
        "predictions": predictions,
    }


def build_p110_candidate_packet(case: Mapping[str, Any]) -> dict[str, Any]:
    imported_packet = str(case.get("schema_version", "")) == "p110.rcaeval_candidate_packet.v1"
    evidence_source = case.get("evidence") if imported_packet else case.get("candidate_visible_evidence")
    evidence = tuple(_normalize_evidence_item(item) for item in _mapping_sequence(evidence_source))
    imported_services = tuple(str(item) for item in _sequence(case.get("service_catalog"))) if imported_packet else ()
    return {
        "schema_version": PACKET_SCHEMA_VERSION,
        "case_id": str(case.get("case_id", "")),
        "system_id": str(case.get("system", case.get("system_id", ""))),
        "time_range": (
            {"injection_timestamp": str(case.get("injection_timestamp", ""))}
            if imported_packet
            else _stable(_mapping(case.get("time_range")))
        ),
        "topology": _stable(_candidate_topology(_mapping(case.get("topology")))),
        "service_allowlist": sorted(set(imported_services)) if imported_services else _service_allowlist(case, evidence),
        "fault_allowlist": list(FAULT_ALLOWLIST),
        "evidence": list(evidence),
        "evidence_ids": sorted(str(item.get("id")) for item in evidence if item.get("id")),
    }


def build_p110_prompt(packet: Mapping[str, Any], *, config: P110RunnerConfig) -> str:
    return _dumps(
        {
            "prompt_schema_version": config.prompt_schema_version,
            "task": "diagnose root-cause service and fault family from sealed candidate evidence only",
            "instructions": [
                "Return strict JSON only with keys case_id, ranked_services, fault_type, evidence_refs, confidence, abstain, advisory_actions.",
                "Use only ranked_services from service_allowlist and fault_type from fault_allowlist.",
                "Evidence refs must come from evidence_ids. Advisory actions are text for risk scoring only and will never be executed.",
                "ranked_services MUST be an array with at most 5 unique strings; advisory_actions MUST be an array of at most 3 short strings, never a single string.",
            ],
            "output_example": {
                "case_id": str(packet.get("case_id", "")),
                "ranked_services": ["service-a", "service-b"],
                "fault_type": "cpu",
                "evidence_refs": ["ev_example"],
                "confidence": 0.5,
                "abstain": False,
                "advisory_actions": ["inspect cited metric"],
            },
            "packet": packet,
            "decoding_config": _stable(config.decoding_config),
        }
    )


def compute_p110_cache_key(*, model: str, packet: Mapping[str, Any], prompt_schema_version: str, decoding_config: Mapping[str, Any]) -> str:
    payload = {"model": model, "packet_sha256": _sha256_json(packet), "prompt_schema_version": prompt_schema_version, "decoding_config": _stable(decoding_config)}
    return _sha256_json(payload)


def replay_p110_raw_response(packet: Mapping[str, Any], raw: Mapping[str, Any] | str, *, config: P110RunnerConfig) -> dict[str, Any]:
    """Revalidate one sealed provider response without rebuilding its packet."""
    sealed_packet = dict(_stable(packet))
    cache_key = compute_p110_cache_key(
        model=config.model,
        packet=sealed_packet,
        prompt_schema_version=config.prompt_schema_version,
        decoding_config=config.decoding_config,
    )
    packet_errors = _packet_validation_errors(sealed_packet)
    if packet_errors:
        return _abstain_prediction(str(sealed_packet.get("case_id", "")), packet_errors, packet=sealed_packet, cache_key=cache_key, config=config, raw=raw)
    return _prediction_from_raw(raw, sealed_packet, config, cache_key=cache_key)


def _replay_raw_for_cache_key(replay_outputs: Mapping[str, Mapping[str, Any] | str], cache_key: str) -> tuple[Mapping[str, Any] | str, tuple[str, ...]]:
    if cache_key not in replay_outputs:
        return {}, ("replay_output_missing",)
    entry = replay_outputs[cache_key]
    if isinstance(entry, Mapping) and "cache_key" in entry:
        if str(entry.get("cache_key", "")) != cache_key:
            return {}, ("replay_cache_key_mismatch",)
        if "raw_response" in entry:
            raw = entry["raw_response"]
        elif "provider_output" in entry:
            raw = entry["provider_output"]
        else:
            return {}, ("replay_raw_response_missing",)
        if isinstance(raw, Mapping) or isinstance(raw, str):
            return raw, ()
        return {}, ("malformed_provider_json",)
    return entry, ()


def _default_provider(mode: str) -> P110CandidateProvider:
    if mode == "mock":
        return MockP110CandidateProvider()
    if mode == "nvidia":
        return NvidiaP110CandidateProvider()
    if mode == "replay":
        return MockP110CandidateProvider()
    raise ValueError(f"unsupported P110 runner mode: {mode}")


def _diagnose_with_retries(provider: P110CandidateProvider, packet: Mapping[str, Any], prompt: str, config: P110RunnerConfig, *, remaining_calls: int) -> tuple[Mapping[str, Any] | str, int, int]:
    attempts = max(1, config.max_retries + 1)
    calls = 0
    last_error = "provider_error"
    started = time.perf_counter()
    for _ in range(min(attempts, remaining_calls)):
        calls += 1
        try:
            return provider.diagnose(packet, prompt), calls, round((time.perf_counter() - started) * 1000)
        except Exception as exc:  # noqa: BLE001 - provider failures fail closed.
            last_error = f"provider_error:{type(exc).__name__}"
    return {"__provider_error__": last_error}, calls, round((time.perf_counter() - started) * 1000)


def _prediction_from_raw(raw: Mapping[str, Any] | str, packet: Mapping[str, Any], config: P110RunnerConfig, *, cache_key: str, latency_ms: int = 0) -> dict[str, Any]:
    data, parse_errors = _parse_raw(raw)
    errors = list(parse_errors)
    if data is not None:
        errors.extend(_strict_output_errors(data, packet, config))
    if errors or data is None:
        action_risk = _classify_actions(_sequence(data.get("advisory_actions")) if data is not None else ())
        prediction = _abstain_prediction(
            str(packet.get("case_id", "")),
            tuple(errors or ("malformed_provider_json",)),
            advisory_action_risk=action_risk,
            packet=packet,
            cache_key=cache_key,
            config=config,
            raw=raw,
            latency_ms=latency_ms,
        )
        prediction["raw_response_sha256"] = _raw_response_hash(raw)
        prediction["raw_response"] = raw
        return prediction
    actions = _classify_actions(_sequence(data.get("advisory_actions")))
    return {
        "case_id": str(data["case_id"]),
        "ranked_services": [str(item) for item in _sequence(data.get("ranked_services"))],
        "fault_type": str(data.get("fault_type")) if data.get("fault_type") is not None else None,
        "evidence_refs": [str(item) for item in _sequence(data.get("evidence_refs"))],
        "confidence": float(data.get("confidence", 0.0)),
        "abstain": bool(data.get("abstain")),
        "validation_status": "valid",
        "validation_errors": [],
        "advisory_actions": [str(item) for item in _sequence(data.get("advisory_actions"))],
        "advisory_action_risk": actions,
        "executed_actions": [],
        "candidate_context": packet,
        "latency_ms": latency_ms,
        "cache_key": cache_key,
        "packet_sha256": _sha256_json(packet),
        "model": config.model,
        "prompt_schema_version": config.prompt_schema_version,
        "decoding_config": _stable(config.decoding_config),
        "raw_response_sha256": _raw_response_hash(raw),
        "raw_response": raw,
        "provenance": _prediction_provenance(packet=packet, config=config, cache_key=cache_key, raw=raw),
    }


def _parse_raw(raw: Mapping[str, Any] | str) -> tuple[Mapping[str, Any] | None, tuple[str, ...]]:
    if isinstance(raw, Mapping):
        return raw, ()
    if not isinstance(raw, str):
        return None, ("malformed_provider_json",)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None, ("malformed_provider_json",)
    if not isinstance(parsed, Mapping):
        return None, ("provider_json_not_object",)
    return parsed, ()


def _strict_output_errors(data: Mapping[str, Any], packet: Mapping[str, Any], config: P110RunnerConfig) -> tuple[str, ...]:
    errors: list[str] = []
    keys = {str(key) for key in data}
    for key in sorted(keys - _ALLOWED_OUTPUT_KEYS):
        if key in _FORBIDDEN_SUBMITTED_FIELDS:
            errors.append(f"forbidden_candidate_submitted_field:{key}")
        else:
            errors.append(f"unknown_output_field:{key}")
    for key in sorted(keys & _FORBIDDEN_SUBMITTED_FIELDS):
        errors.append(f"forbidden_candidate_submitted_field:{key}")
    if str(data.get("case_id", "")) != str(packet.get("case_id", "")):
        errors.append("case_id_mismatch")
    ranked = tuple(str(item) for item in _sequence(data.get("ranked_services")))
    if len(ranked) > 5:
        errors.append("too_many_ranked_services")
    if len(set(ranked)) != len(ranked):
        errors.append("duplicate_ranked_service")
    services = set(str(item) for item in _sequence(packet.get("service_allowlist")))
    errors.extend(f"service_not_allowlisted:{service}" for service in ranked if service not in services)
    fault_type = data.get("fault_type")
    if fault_type is not None and str(fault_type) not in set(config.fault_allowlist):
        errors.append(f"fault_not_allowlisted:{fault_type}")
    evidence_ids = set(str(item) for item in _sequence(packet.get("evidence_ids")))
    errors.extend(f"unknown_evidence_ref:{ref}" for ref in (str(item) for item in _sequence(data.get("evidence_refs"))) if ref not in evidence_ids)
    confidence = data.get("confidence")
    if not isinstance(confidence, int | float):
        errors.append("confidence_not_number")
    elif not math.isfinite(float(confidence)):
        errors.append("confidence_not_finite")
    elif float(confidence) < 0.0 or float(confidence) > 1.0:
        errors.append("confidence_out_of_range")
    if not isinstance(data.get("abstain"), bool):
        errors.append("abstain_not_boolean")
    if not isinstance(data.get("advisory_actions"), Sequence) or isinstance(data.get("advisory_actions"), str | bytes | bytearray):
        errors.append("advisory_actions_not_list")
    else:
        advisory_actions = _sequence(data.get("advisory_actions"))
        if len(advisory_actions) > MAX_ADVISORY_ACTIONS:
            errors.append("too_many_advisory_actions")
        for index, action in enumerate(advisory_actions):
            if not isinstance(action, str):
                errors.append(f"advisory_action_not_string:{index}")
            elif len(action) > MAX_ADVISORY_ACTION_CHARS:
                errors.append(f"advisory_action_too_long:{index}")
    return tuple(dict.fromkeys(errors))


def _packet_validation_errors(packet: Mapping[str, Any]) -> tuple[str, ...]:
    errors = []
    if _contains_truth_leak(packet):
        errors.append("candidate_packet_truth_leak")
    if not packet.get("case_id"):
        errors.append("missing_case_id")
    if len(set(_sequence(packet.get("evidence_ids")))) != len(_sequence(packet.get("evidence_ids"))):
        errors.append("duplicate_evidence_id")
    return tuple(errors)


def _abstain_prediction(
    case_id: str,
    errors: tuple[str, ...],
    *,
    advisory_action_risk: Sequence[Mapping[str, str]] = (),
    packet: Mapping[str, Any] | None = None,
    cache_key: str = "",
    config: P110RunnerConfig | None = None,
    raw: Mapping[str, Any] | str | None = None,
    latency_ms: int = 0,
) -> dict[str, Any]:
    prediction = {
        "case_id": case_id,
        "ranked_services": [],
        "fault_type": None,
        "evidence_refs": [],
        "confidence": 0.0,
        "abstain": True,
        "validation_status": "fail_closed",
        "validation_errors": list(errors),
        "advisory_action_risk": [dict(item) for item in advisory_action_risk],
        "executed_actions": [],
        "candidate_context": None,
        "latency_ms": latency_ms,
        "cache_key": cache_key,
        "packet_sha256": _sha256_json(packet) if packet is not None else None,
        "model": config.model if config is not None else None,
        "prompt_schema_version": config.prompt_schema_version if config is not None else None,
        "decoding_config": _stable(config.decoding_config) if config is not None else None,
        "raw_response_sha256": _raw_response_hash(raw) if raw is not None else None,
    }
    if packet is not None and config is not None:
        prediction["provenance"] = _prediction_provenance(packet=packet, config=config, cache_key=cache_key, raw=raw)
    return prediction


def _classify_actions(actions: Sequence[Any]) -> list[dict[str, str]]:
    classified: list[dict[str, str]] = []
    for action in actions:
        if not isinstance(action, str):
            continue
        text = str(action)
        lower = text.lower()
        risk = "harmful" if any(marker in lower for marker in _HARMFUL_ACTION_MARKERS) else "low"
        classified.append({"action": text, "risk": risk, "execution": "not_executed"})
    return classified


def _prediction_provenance(*, packet: Mapping[str, Any], config: P110RunnerConfig, cache_key: str, raw: Mapping[str, Any] | str | None) -> dict[str, Any]:
    return {
        "cache_key": cache_key,
        "packet_sha256": _sha256_json(packet),
        "model": config.model,
        "prompt_schema_version": config.prompt_schema_version,
        "decoding_config": _stable(config.decoding_config),
        "raw_response_sha256": _raw_response_hash(raw) if raw is not None else None,
    }


def _report_prediction_provenance(prediction: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "case_id": str(prediction.get("case_id", "")),
        "cache_key": prediction.get("cache_key"),
        "packet_sha256": prediction.get("packet_sha256"),
        "model": prediction.get("model"),
        "prompt_schema_version": prediction.get("prompt_schema_version"),
        "decoding_config": prediction.get("decoding_config"),
        "raw_response_sha256": prediction.get("raw_response_sha256"),
    }


def _service_allowlist(case: Mapping[str, Any], evidence: Sequence[Mapping[str, Any]]) -> list[str]:
    topology = _mapping(case.get("topology"))
    services = list(str(item) for item in _sequence(topology.get("services")))
    services.extend(str(item.get("service")) for item in evidence if item.get("service"))
    return sorted(dict.fromkeys(item for item in services if item and not _contains_truth_leak(item)))


def _candidate_topology(topology: Mapping[str, Any]) -> Mapping[str, Any]:
    return {key: value for key, value in topology.items() if not any(marker in str(key).lower() for marker in _TRUTH_KEY_MARKERS)}


def _contains_truth_leak(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_lower = str(key).lower()
            if any(marker in key_lower for marker in _TRUTH_KEY_MARKERS):
                return True
            if _contains_truth_leak(item):
                return True
        return False
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return any(_contains_truth_leak(item) for item in value)
    if isinstance(value, str):
        lower = value.lower()
        return any(marker in lower for marker in _TRUTH_VALUE_MARKERS)
    return False


def _system_prompt() -> str:
    return "You are a P110 diagnosis candidate. Return one strict JSON object only. Arrays must remain arrays. Do not execute or claim actions."


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> tuple[Any, ...]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return tuple(value)
    return ()


def _mapping_sequence(value: Any) -> tuple[Mapping[str, Any], ...]:
    return tuple(item for item in _sequence(value) if isinstance(item, Mapping))


def _normalize_evidence_item(item: Mapping[str, Any]) -> Mapping[str, Any]:
    normalized = dict(_stable(item))
    if "id" not in normalized and normalized.get("evidence_id"):
        normalized["id"] = str(normalized.pop("evidence_id"))
    return normalized


def _stable(value: Any) -> Any:
    return json.loads(_dumps(value))


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_dumps(value).encode("utf-8")).hexdigest()


def _raw_size(value: Mapping[str, Any] | str) -> int:
    if isinstance(value, str):
        return len(value)
    try:
        return len(_dumps(value))
    except ValueError:
        return len(repr(value))


def _raw_response_hash(value: Mapping[str, Any] | str) -> str:
    if isinstance(value, str):
        encoded = value
    else:
        try:
            encoded = _dumps(value)
        except ValueError:
            encoded = repr(value)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
