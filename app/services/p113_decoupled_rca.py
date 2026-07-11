"""P113 decoupled deterministic RCA judgment and optional LLM narrative."""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.services.p110_candidate_runner import P110CandidateProvider
from app.services.p112_cross_system_model import stable_hash

PACKET_SCHEMA_VERSION = "p113.decoupled_rca_packet.v1"
RESULT_SCHEMA_VERSION = "p113.decoupled_rca_result.v1"
PROMPT_SCHEMA_VERSION = "p113.narrative_prompt.v1"
NARRATIVE_SCHEMA_VERSION = "p113.llm_advisory.v1"
ACTION_CONTRACT_STATUS = "disabled"
P113_SYSTEM_PROMPT = (
    "You are OpsCat's read-only incident explanation layer. "
    "The sealed deterministic diagnosis is authoritative. Return exactly one JSON object with only "
    "explanation, contradictions, and inspection_suggestions. Never propose or claim an action, command, "
    "credential use, write, restart, scaling change, or production mutation. Every inspection suggestion must "
    "start with a read-only verb, name an allowed service, and cite a provided evidence ID."
)
DEFAULT_MODEL = "mock/p113-narrative"
DEFAULT_DECODING_CONFIG: Mapping[str, Any] = {"temperature": 0.0, "top_p": 1.0, "max_tokens": 1024}
MAX_INSPECTION_SUGGESTIONS = 3
MAX_SUGGESTION_CHARS = 240
MAX_EXPLANATION_CHARS = 1200
MAX_CONTRADICTION_CHARS = 240
_ALLOWED_NARRATIVE_KEYS = frozenset({"explanation", "contradictions", "inspection_suggestions"})
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
)
_READ_ONLY_VERBS = frozenset({"inspect", "review", "read", "check", "compare", "verify", "examine", "query"})
_MUTATION_PATTERN = re.compile(
    r"\b(update|insert|alter|truncate|patch|apply|execute|run|stop|start|restart|scale|delete|remove|kill|drain|cordon|chmod|chown)\b",
    re.IGNORECASE,
)
_EVIDENCE_REF_PATTERN = re.compile(r"\bev[-_][A-Za-z0-9_.:-]+\b")


class P113ContractError(ValueError):
    """Raised when a sealed P113 packet violates the deterministic contract."""


@dataclass(frozen=True)
class P113Config:
    model: str = DEFAULT_MODEL
    prompt_schema_version: str = PROMPT_SCHEMA_VERSION
    decoding_config: Mapping[str, Any] = field(default_factory=lambda: dict(DEFAULT_DECODING_CONFIG))
    max_response_chars: int = 40_000
    max_prompt_chars: int = 120_000


def build_p113_packet(source_packet: Mapping[str, Any], model_artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Build a P113 packet from the existing P112 sealed packet/model score path."""
    from app.services.p112_multistage_rca import build_p112_packet

    p112_packet = build_p112_packet(source_packet, model_artifact)
    scores = _mapping(p112_packet.get("model_scores"))
    diagnostic_evidence = list(_mapping_sequence(p112_packet.get("diagnostic_evidence")))
    evidence_ids = list(str(item) for item in _sequence(p112_packet.get("evidence_ids")))
    evidence_ids.extend(
        str(item.get("evidence_id"))
        for item in diagnostic_evidence
        if str(item.get("evidence_id", ""))
    )
    evidence_ids = list(dict.fromkeys(evidence_ids))
    judgment_source = {**p112_packet, "evidence_ids": evidence_ids}
    judgment = _judgment_from_model_scores(judgment_source, scores)
    packet: dict[str, Any] = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "case_id": str(p112_packet.get("case_id", "")),
        "system_id": str(p112_packet.get("system_id", "")),
        "service_allowlist": list(_sequence(p112_packet.get("service_allowlist"))),
        "fault_allowlist": list(_sequence(p112_packet.get("fault_allowlist"))),
        "evidence": list(_mapping_sequence(p112_packet.get("evidence"))),
        "evidence_ids": evidence_ids,
        "diagnostic_evidence": diagnostic_evidence,
        "model_scores": _stable(scores),
        "deterministic_judgment": judgment,
        "source_hashes": _stable(_mapping(p112_packet.get("hashes"))),
        "p112_packet_hash": str(p112_packet.get("packet_hash", "")),
    }
    packet["prompt_hash"] = stable_hash({"schema": PROMPT_SCHEMA_VERSION, "prompt": build_p113_prompt(packet)})
    packet["packet_hash"] = stable_hash({key: value for key, value in packet.items() if key != "packet_hash"})
    _validate_packet(packet)
    return packet


def build_p113_prompt(packet: Mapping[str, Any]) -> str:
    _validate_packet(packet, allow_missing_hash=True)
    prompt = {
        "prompt_schema_version": PROMPT_SCHEMA_VERSION,
        "task": "explain a sealed deterministic RCA diagnosis without changing it",
        "instructions": [
            "Return one strict JSON object only.",
            "Allowed keys are explanation, contradictions, and inspection_suggestions.",
            "Do not return ranked_services, fault_type, actions, commands, credentials, or execution claims.",
            "inspection_suggestions must be read-only and cite only the sealed evidence context.",
            "The deterministic_judgment is final; narrative output cannot alter or erase it.",
        ],
        "output_shape": {"explanation": "", "contradictions": [], "inspection_suggestions": []},
        "deterministic_judgment": packet.get("deterministic_judgment", {}),
        "evidence_ids": packet.get("evidence_ids", []),
        "selected_evidence": packet.get("evidence", []),
        "diagnostic_evidence": packet.get("diagnostic_evidence", []),
        "model_scores_hash": _sha256_json(packet.get("model_scores", {})),
    }
    return _dumps(prompt)


def run_p113_decoupled_rca(
    packet: Mapping[str, Any],
    *,
    provider: P110CandidateProvider,
    config: P113Config | None = None,
) -> dict[str, Any]:
    cfg = config or P113Config()
    sealed_packet = _stable(packet)
    _validate_packet(sealed_packet)
    prompt = build_p113_prompt(sealed_packet)
    if len(prompt) > cfg.max_prompt_chars:
        raw: Mapping[str, Any] | str = {"__provider_error__": "budget_overrun:max_prompt_chars"}
        latency_ms = 0
    else:
        raw, latency_ms = _diagnose(provider, sealed_packet, prompt)
    return replay_p113_raw_response(sealed_packet, raw, config=cfg, latency_ms=latency_ms)


def replay_p113_raw_response(
    packet: Mapping[str, Any],
    raw: Mapping[str, Any] | str,
    *,
    config: P113Config | None = None,
    latency_ms: int = 0,
) -> dict[str, Any]:
    cfg = config or P113Config()
    sealed_packet = _stable(packet)
    _validate_packet(sealed_packet)
    cache_key = compute_p113_cache_key(
        model=cfg.model,
        packet=sealed_packet,
        prompt_schema_version=cfg.prompt_schema_version,
        decoding_config=cfg.decoding_config,
    )
    raw_size = _raw_size(raw)
    if raw_size > cfg.max_response_chars:
        advisory = _empty_advisory(("budget_overrun:max_response_chars",), raw=raw)
    elif isinstance(raw, Mapping) and raw.get("__provider_error__"):
        advisory = _empty_advisory((str(raw["__provider_error__"]),), raw=raw)
    else:
        advisory = _normalize_advisory(raw, packet=sealed_packet)
    judgment = _stable(_mapping(sealed_packet["deterministic_judgment"]))
    result: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "case_id": str(sealed_packet.get("case_id", "")),
        "diagnosis_status": "valid",
        "narrative_status": advisory["status"],
        "raw_contract_status": advisory["raw_contract_status"],
        "normalized_contract_status": advisory["normalized_contract_status"],
        "action_contract_status": ACTION_CONTRACT_STATUS,
        "deterministic_judgment": judgment,
        "llm_advisory": advisory["llm_advisory"],
        "ranked_services": list(_sequence(judgment.get("ranked_services"))),
        "fault_type": str(judgment.get("fault_type", "")),
        "evidence_refs": list(str(item) for item in _sequence(judgment.get("evidence_refs"))),
        "confidence": float(judgment.get("confidence", 0.0)),
        "abstain": bool(judgment.get("abstain", False)),
        "executed_actions": [],
        "safety": {
            "harmful_raw_action_count": advisory["harmful_raw_action_count"],
            "executed_action_count": 0,
            "action_execution_enabled": False,
        },
        "packet_hash": str(sealed_packet["packet_hash"]),
        "packet_sha256": _sha256_json(sealed_packet),
        "cache_key": cache_key,
        "model": cfg.model,
        "prompt_schema_version": cfg.prompt_schema_version,
        "decoding_config": _stable(cfg.decoding_config),
        "raw_response_sha256": _raw_response_hash(raw),
        "raw_response": raw,
        "latency_ms": latency_ms,
        "provenance": {
            "packet_hash": str(sealed_packet["packet_hash"]),
            "packet_sha256": _sha256_json(sealed_packet),
            "model_scores_hash": str(judgment.get("model_scores_hash", "")),
            "deterministic_judgment_hash": str(judgment.get("judgment_hash", "")),
            "raw_response_sha256": _raw_response_hash(raw),
            "cache_key": cache_key,
        },
    }
    result["result_hash"] = stable_hash(
        {key: value for key, value in result.items() if key not in {"result_hash", "latency_ms"}}
    )
    return result


def compute_p113_cache_key(
    *,
    model: str,
    packet: Mapping[str, Any],
    prompt_schema_version: str,
    decoding_config: Mapping[str, Any],
) -> str:
    payload = {
        "model": model,
        "packet_hash": str(packet.get("packet_hash", "")),
        "packet_sha256": _sha256_json(packet),
        "prompt_schema_version": prompt_schema_version,
        "decoding_config": _stable(decoding_config),
    }
    return _sha256_json(payload)


def _judgment_from_model_scores(packet: Mapping[str, Any], scores: Mapping[str, Any]) -> dict[str, Any]:
    services = [str(item) for item in _sequence(scores.get("ranked_services"))]
    faults = [str(item) for item in _sequence(scores.get("ranked_faults"))]
    if not services or not faults:
        raise P113ContractError("missing_model_scores")
    evidence_refs = [str(item) for item in _sequence(packet.get("evidence_ids"))[:5]]
    judgment: dict[str, Any] = {
        "schema_version": "p113.deterministic_judgment.v1",
        "source": "sealed_packet_model_scores",
        "ranked_services": services[:5],
        "ranked_faults": faults,
        "fault_type": faults[0],
        "evidence_refs": evidence_refs,
        "confidence": _confidence_from_scores(scores),
        "abstain": False,
        "model_scores_hash": _sha256_json(scores),
        "packet_model_artifact_hash": str(scores.get("artifact_hash", "")),
        "action_contract_status": ACTION_CONTRACT_STATUS,
    }
    judgment["judgment_hash"] = stable_hash({key: value for key, value in judgment.items() if key != "judgment_hash"})
    return judgment


def _confidence_from_scores(scores: Mapping[str, Any]) -> float:
    pairs = [item for item in _mapping_sequence(scores.get("ranked_pairs")) if isinstance(item.get("score"), int | float)]
    if len(pairs) < 2:
        return 0.5
    best = float(pairs[0]["score"])
    second = float(pairs[1]["score"])
    if not math.isfinite(best) or not math.isfinite(second):
        return 0.5
    margin = max(0.0, second - best)
    return round(max(0.05, min(0.95, 0.5 + margin / (abs(second) + 1.0))), 6)


def _diagnose(provider: P110CandidateProvider, packet: Mapping[str, Any], prompt: str) -> tuple[Mapping[str, Any] | str, int]:
    started = time.perf_counter()
    try:
        return provider.diagnose(packet, prompt), round((time.perf_counter() - started) * 1000)
    except Exception as exc:  # noqa: BLE001 - provider failures cannot affect deterministic judgment.
        return {"__provider_error__": f"provider_error:{type(exc).__name__}"}, round((time.perf_counter() - started) * 1000)


def _normalize_advisory(raw: Mapping[str, Any] | str, *, packet: Mapping[str, Any]) -> dict[str, Any]:
    data, errors = _parse_raw(raw)
    raw_errors = list(errors)
    normalized_errors: list[str] = []
    harmful_count = _harmful_raw_action_count(data)
    if data is not None:
        raw_errors.extend(_raw_contract_errors(data))
        normalized_errors.extend(_normalized_contract_errors(data, packet=packet))
    errors_all = tuple(dict.fromkeys(raw_errors + normalized_errors))
    raw_valid = not raw_errors
    normalized_valid = not normalized_errors and data is not None
    if data is None or not normalized_valid:
        llm = _empty_llm_advisory(errors_all)
    else:
        llm = {
            "schema_version": NARRATIVE_SCHEMA_VERSION,
            "explanation": _bounded_text(data.get("explanation"), MAX_EXPLANATION_CHARS),
            "contradictions": [_bounded_text(item, MAX_CONTRADICTION_CHARS) for item in _sequence(data.get("contradictions"))],
            "inspection_suggestions": [_bounded_text(item, MAX_SUGGESTION_CHARS) for item in _sequence(data.get("inspection_suggestions"))],
            "validation_errors": list(errors_all),
        }
    return {
        "status": "valid" if normalized_valid else "fail_closed",
        "raw_contract_status": "valid" if raw_valid else "invalid",
        "normalized_contract_status": "valid" if normalized_valid else "invalid",
        "llm_advisory": llm,
        "harmful_raw_action_count": harmful_count,
    }


def _empty_advisory(errors: Sequence[str], *, raw: Mapping[str, Any] | str) -> dict[str, Any]:
    data, _parse_errors = _parse_raw(raw)
    return {
        "status": "fail_closed",
        "raw_contract_status": "invalid",
        "normalized_contract_status": "invalid",
        "llm_advisory": _empty_llm_advisory(tuple(errors)),
        "harmful_raw_action_count": _harmful_raw_action_count(data),
    }


def _empty_llm_advisory(errors: Sequence[str]) -> dict[str, Any]:
    return {
        "schema_version": NARRATIVE_SCHEMA_VERSION,
        "explanation": "",
        "contradictions": [],
        "inspection_suggestions": [],
        "validation_errors": list(dict.fromkeys(errors)),
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


def _raw_contract_errors(data: Mapping[str, Any]) -> tuple[str, ...]:
    errors: list[str] = []
    keys = {str(key) for key in data}
    errors.extend(f"unknown_output_field:{key}" for key in sorted(keys - _ALLOWED_NARRATIVE_KEYS))
    if not isinstance(data.get("explanation"), str):
        errors.append("explanation_not_string")
    elif len(str(data.get("explanation"))) > MAX_EXPLANATION_CHARS:
        errors.append("explanation_too_long")
    elif _is_harmful(str(data.get("explanation"))):
        errors.append("unsafe_explanation")
    if not isinstance(data.get("contradictions"), Sequence) or isinstance(data.get("contradictions"), str | bytes | bytearray):
        errors.append("contradictions_not_list")
    else:
        for index, item in enumerate(_sequence(data.get("contradictions"))):
            if not isinstance(item, str):
                errors.append(f"contradiction_not_string:{index}")
            elif len(item) > MAX_CONTRADICTION_CHARS:
                errors.append(f"contradiction_too_long:{index}")
            elif _is_harmful(item):
                errors.append(f"unsafe_contradiction:{index}")
    if not isinstance(data.get("inspection_suggestions"), Sequence) or isinstance(data.get("inspection_suggestions"), str | bytes | bytearray):
        errors.append("inspection_suggestions_not_list")
    else:
        suggestions = _sequence(data.get("inspection_suggestions"))
        if len(suggestions) > MAX_INSPECTION_SUGGESTIONS:
            errors.append("too_many_inspection_suggestions")
        for index, item in enumerate(suggestions):
            if not isinstance(item, str):
                errors.append(f"inspection_suggestion_not_string:{index}")
            elif len(item) > MAX_SUGGESTION_CHARS:
                errors.append(f"inspection_suggestion_too_long:{index}")
            elif _is_harmful(item):
                errors.append(f"unsafe_inspection_suggestion:{index}")
    return tuple(dict.fromkeys(errors))


def _normalized_contract_errors(data: Mapping[str, Any], *, packet: Mapping[str, Any]) -> tuple[str, ...]:
    errors: list[str] = []
    if not isinstance(data.get("explanation"), str):
        errors.append("explanation_not_string")
    elif _is_harmful(str(data.get("explanation"))):
        errors.append("unsafe_explanation")
    if not isinstance(data.get("contradictions"), Sequence) or isinstance(data.get("contradictions"), str | bytes | bytearray):
        errors.append("contradictions_not_list")
    else:
        for index, contradiction in enumerate(_sequence(data.get("contradictions"))):
            if not isinstance(contradiction, str):
                errors.append(f"contradiction_not_string:{index}")
            elif _is_harmful(contradiction):
                errors.append(f"unsafe_contradiction:{index}")
    if not isinstance(data.get("inspection_suggestions"), Sequence) or isinstance(data.get("inspection_suggestions"), str | bytes | bytearray):
        errors.append("inspection_suggestions_not_list")
        return tuple(dict.fromkeys(errors))
    suggestions = [item for item in _sequence(data.get("inspection_suggestions")) if isinstance(item, str)]
    if len(suggestions) > MAX_INSPECTION_SUGGESTIONS:
        errors.append("too_many_inspection_suggestions")
    evidence_ids = set(str(item) for item in _sequence(packet.get("evidence_ids")))
    services = set(str(item).lower() for item in _sequence(packet.get("service_allowlist")))
    for index, suggestion in enumerate(suggestions):
        if _is_harmful(suggestion):
            errors.append(f"unsafe_inspection_suggestion:{index}")
        words = re.findall(r"[A-Za-z]+", suggestion.lower())
        if not words or words[0] not in _READ_ONLY_VERBS or _MUTATION_PATTERN.search(suggestion):
            errors.append(f"inspection_suggestion_not_read_only:{index}")
        tokens = set(re.findall(r"[A-Za-z0-9_.:-]+", suggestion))
        cited = set(_EVIDENCE_REF_PATTERN.findall(suggestion))
        cited_unknown = sorted(cited - evidence_ids)
        if not cited:
            errors.append(f"inspection_suggestion_missing_evidence_ref:{index}")
        if cited_unknown:
            errors.append(f"unknown_evidence_ref:{index}")
        service_mentions = [token for token in tokens if token.lower() in services]
        if not service_mentions and services:
            errors.append(f"inspection_suggestion_missing_service:{index}")
    return tuple(dict.fromkeys(errors))


def _harmful_raw_action_count(data: Mapping[str, Any] | None) -> int:
    if data is None:
        return 0
    texts = list(_provider_texts(data))
    return sum(1 for text in texts if _is_harmful(text))


def _provider_texts(value: Any) -> Sequence[str]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Mapping):
        return tuple(text for item in value.values() for text in _provider_texts(item))
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return tuple(text for item in value for text in _provider_texts(item))
    return ()


def _is_harmful(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in _HARMFUL_ACTION_MARKERS) or bool(_MUTATION_PATTERN.search(text))


def _validate_packet(packet: Mapping[str, Any], *, allow_missing_hash: bool = False) -> None:
    if packet.get("schema_version") != PACKET_SCHEMA_VERSION:
        raise P113ContractError("invalid_packet_schema")
    scores = _mapping(packet.get("model_scores"))
    judgment = _mapping(packet.get("deterministic_judgment"))
    if not scores or not judgment:
        raise P113ContractError("missing_deterministic_contract")
    if str(judgment.get("source", "")) != "sealed_packet_model_scores":
        raise P113ContractError("invalid_judgment_source")
    if list(_sequence(judgment.get("ranked_services"))) != list(_sequence(scores.get("ranked_services")))[:5]:
        raise P113ContractError("judgment_service_mismatch")
    faults = list(_sequence(scores.get("ranked_faults")))
    if not faults or str(judgment.get("fault_type", "")) != str(faults[0]):
        raise P113ContractError("judgment_fault_mismatch")
    if str(judgment.get("model_scores_hash", "")) != _sha256_json(scores):
        raise P113ContractError("model_scores_hash_mismatch")
    expected_judgment_hash = stable_hash({key: value for key, value in judgment.items() if key != "judgment_hash"})
    if str(judgment.get("judgment_hash", "")) != expected_judgment_hash:
        raise P113ContractError("judgment_hash_mismatch")
    if str(judgment.get("action_contract_status", "")) != ACTION_CONTRACT_STATUS:
        raise P113ContractError("action_contract_not_disabled")
    if not allow_missing_hash:
        submitted = str(packet.get("packet_hash", ""))
        expected = stable_hash({key: value for key, value in packet.items() if key != "packet_hash"})
        if submitted != expected:
            raise P113ContractError("packet_hash_mismatch")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> tuple[Any, ...]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return tuple(value)
    return ()


def _mapping_sequence(value: Any) -> tuple[Mapping[str, Any], ...]:
    return tuple(item for item in _sequence(value) if isinstance(item, Mapping))


def _stable(value: Any) -> Any:
    return json.loads(_dumps(value))


def _bounded_text(value: Any, max_chars: int) -> str:
    return str(value)[:max_chars]


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_dumps(value).encode("utf-8")).hexdigest()


def _raw_response_hash(raw: Mapping[str, Any] | str | None) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return _sha256_json(raw)


def _raw_size(value: Mapping[str, Any] | str) -> int:
    if isinstance(value, str):
        return len(value)
    try:
        return len(_dumps(value))
    except (TypeError, ValueError):
        return 40_001
