"""Constrained, replayable LLM adjudication over a frozen P114 hypothesis lattice."""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.services.p110_candidate_runner import P110CandidateProvider
from app.services.p110_evaluation import stable_hash
from app.services.p114_hypothesis_lattice import LATTICE_SCHEMA_VERSION
from app.services.p114_re2_loader import CANDIDATE_SCHEMA_VERSION

PACKET_SCHEMA_VERSION = "p114.adjudication_packet.v1"
RESULT_SCHEMA_VERSION = "p114.adjudication_result.v1"
PROMPT_SCHEMA_VERSION = "p114.adjudication_prompt.v1"
DEFAULT_MODEL = "mock/p114-adjudicator"
DEFAULT_DECODING_CONFIG: Mapping[str, Any] = {
    "temperature": 1.0,
    "top_p": 0.95,
    "max_tokens": 3072,
    "enable_thinking": True,
    "reasoning_budget": 2048,
}
P114_SYSTEM_PROMPT = (
    "You are a read-only incident evidence adjudicator. Select only one supplied hypothesis ID and only supplied "
    "evidence IDs. Return exactly one JSON object. Never generate services, faults, actions, commands, credentials, "
    "writes, mutations, or remediation instructions. If evidence is insufficient, abstain."
)
_ALLOWED_KEYS = frozenset({"hypothesis_id", "abstain"})
_FORBIDDEN_TEXT = re.compile(
    r"\b(kubectl|sudo|restart|delete|remove|drop|update|insert|alter|execute|run|scale|kill|chmod|chown|token|password|api[_ -]?key|secret)\b",
    re.IGNORECASE,
)


class P114AdjudicationError(ValueError):
    """Raised when adjudication inputs violate their sealed contract."""


@dataclass(frozen=True)
class P114AdjudicatorConfig:
    model: str = DEFAULT_MODEL
    prompt_schema_version: str = PROMPT_SCHEMA_VERSION
    decoding_config: Mapping[str, Any] = field(default_factory=lambda: dict(DEFAULT_DECODING_CONFIG))
    max_prompt_chars: int = 120_000
    max_response_chars: int = 20_000


class NvidiaP114AdjudicatorProvider:
    """Bounded NVIDIA provider dedicated to strict P114 candidate selection."""

    name = "nvidia"
    model_calls_enabled = True

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "nvidia/nemotron-3-nano-30b-a3b",
        client: Any | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY")
        if client is None and not self.api_key:
            raise RuntimeError("NVIDIA_API_KEY is required for explicit P114 NVIDIA mode")
        self.model = model
        self._client = client

    def diagnose(self, packet: Mapping[str, Any], prompt: str) -> Mapping[str, Any] | str:
        client = self._client or self._build_client()
        profile = nvidia_decoding_config(self.model)
        completion = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": P114_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=profile["temperature"],
            top_p=profile["top_p"],
            max_tokens=profile["max_tokens"],
            extra_body=profile["extra_body"],
            stream=False,
        )
        choices = getattr(completion, "choices", None)
        if not choices:
            raise ValueError("NVIDIA response contained no choices")
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise ValueError("NVIDIA response contained no content")
        return content.strip()

    def _build_client(self) -> Any:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("install the optional openai client before using P114 NVIDIA mode") from exc
        return OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=self.api_key,
            timeout=90.0,
            max_retries=0,
        )


def nvidia_decoding_config(model: str) -> dict[str, Any]:
    """Return the official-family request profile with a bounded reasoning budget."""
    if model == "nvidia/nemotron-3-nano-30b-a3b":
        return {
            "temperature": 0.6,
            "top_p": 0.95,
            "max_tokens": 512,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        }
    if model == "nvidia/nvidia-nemotron-nano-9b-v2":
        return {
            "temperature": 0.6,
            "top_p": 0.95,
            "max_tokens": 2048,
            "extra_body": {"min_thinking_tokens": 512, "max_thinking_tokens": 1024},
        }
    if model in {
        "nvidia/nemotron-3-super-120b-a12b",
        "nvidia/nemotron-3-ultra-550b-a55b",
    }:
        return {
            "temperature": 0.6,
            "top_p": 0.95,
            "max_tokens": 512,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        }
    return {
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 3072,
        "extra_body": {
            "chat_template_kwargs": {"enable_thinking": True},
            "reasoning_budget": 2048,
        },
    }


def build_p114_adjudication_packet(candidate_packet: Mapping[str, Any], lattice: Mapping[str, Any]) -> dict[str, Any]:
    _validate_candidate_and_lattice(candidate_packet, lattice)
    nodes = [_mapping(item) for item in _sequence(_mapping(candidate_packet.get("evidence_graph")).get("nodes"))]
    evidence_by_id = {str(node.get("node_id", "")): node for node in nodes}
    cited_ids = {
        str(evidence_id)
        for hypothesis in _mapping_sequence(lattice.get("hypotheses"))
        for field_name in ("supporting_evidence_ids", "contradicting_evidence_ids")
        for evidence_id in _sequence(hypothesis.get(field_name))
    }
    selected_evidence = [
        {
            "node_id": evidence_id,
            "modality": evidence_by_id[evidence_id].get("modality"),
            "subject": evidence_by_id[evidence_id].get("subject"),
            "signal": evidence_by_id[evidence_id].get("signal"),
            "pre_value": evidence_by_id[evidence_id].get("pre_value"),
            "post_value": evidence_by_id[evidence_id].get("post_value"),
            "delta": evidence_by_id[evidence_id].get("delta"),
            "support": list(_sequence(evidence_by_id[evidence_id].get("support"))),
            "contradiction": list(_sequence(evidence_by_id[evidence_id].get("contradiction"))),
            "missing": list(_sequence(evidence_by_id[evidence_id].get("missing"))),
        }
        for evidence_id in sorted(cited_ids)
        if evidence_id in evidence_by_id
    ]
    payload: dict[str, Any] = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "case_id": str(lattice["case_id"]),
        "candidate_packet_hash": stable_hash(candidate_packet),
        "lattice_hash": str(lattice["lattice_hash"]),
        "hypotheses": sorted(
            [
                {
                    "hypothesis_id": str(item.get("hypothesis_id", "")),
                    "service": str(item.get("service", "")),
                    "fault": str(item.get("fault", "")),
                    "supporting_evidence_ids": list(_sequence(item.get("supporting_evidence_ids"))),
                    "contradicting_evidence_ids": list(_sequence(item.get("contradicting_evidence_ids"))),
                    "missing_evidence": list(_sequence(item.get("missing_evidence"))),
                }
                for item in _mapping_sequence(lattice.get("hypotheses"))
            ],
            key=lambda item: item["hypothesis_id"],
        ),
        "deterministic_fallback_hypothesis_id": str(_mapping_sequence(lattice.get("hypotheses"))[0].get("hypothesis_id", "")),
        "evidence": selected_evidence,
        "action_contract_status": "disabled",
    }
    payload["packet_hash"] = stable_hash(payload)
    return payload


def build_p114_adjudication_prompt(packet: Mapping[str, Any]) -> str:
    _validate_packet(packet)
    public_packet = {key: value for key, value in packet.items() if key not in {"deterministic_fallback_hypothesis_id", "packet_hash"}}
    return json.dumps(
        {
            "prompt_schema_version": PROMPT_SCHEMA_VERSION,
            "task": "select the best supplied service-fault hypothesis using only cited evidence",
            "instructions": [
                "Return strict JSON with exactly hypothesis_id and abstain.",
                "Select one hypothesis_id from hypotheses, or set hypothesis_id to an empty string when abstaining.",
                "Evidence is already cryptographically bound to each hypothesis and the system attaches it; do not return evidence_ids.",
                "When hypothesis_id is non-empty, abstain must be false. When abstain is true, hypothesis_id must be empty.",
                "Do not invent IDs, services, faults, actions, commands, credentials, or mutation text.",
            ],
            "output_shape": {"hypothesis_id": "", "abstain": True},
            "packet": public_packet,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def run_p114_adjudication(
    packet: Mapping[str, Any],
    *,
    provider: P110CandidateProvider,
    config: P114AdjudicatorConfig | None = None,
) -> dict[str, Any]:
    cfg = config or P114AdjudicatorConfig()
    _validate_packet(packet)
    prompt = build_p114_adjudication_prompt(packet)
    if len(prompt) > cfg.max_prompt_chars:
        raw: Mapping[str, Any] | str = {"__provider_error__": "budget_overrun:max_prompt_chars"}
        latency_ms = 0
    else:
        started = time.perf_counter()
        try:
            raw = provider.diagnose(packet, prompt)
        except Exception as exc:  # noqa: BLE001 - provider failure must preserve fallback.
            raw = {"__provider_error__": f"provider_error:{type(exc).__name__}"}
        latency_ms = round((time.perf_counter() - started) * 1000)
    return replay_p114_adjudication(packet, raw, config=cfg, latency_ms=latency_ms)


def replay_p114_adjudication(
    packet: Mapping[str, Any],
    raw: Mapping[str, Any] | str,
    *,
    config: P114AdjudicatorConfig | None = None,
    latency_ms: int = 0,
) -> dict[str, Any]:
    cfg = config or P114AdjudicatorConfig()
    _validate_packet(packet)
    hypotheses = _mapping_sequence(packet.get("hypotheses"))
    fallback_id = str(packet.get("deterministic_fallback_hypothesis_id", ""))
    fallback = next(
        (item for item in hypotheses if str(item.get("hypothesis_id", "")) == fallback_id),
        {},
    )
    if not fallback:
        raise P114AdjudicationError("missing_deterministic_fallback")
    errors: list[str] = []
    data = _parse_raw(raw, errors)
    if _raw_size(raw) > cfg.max_response_chars:
        errors.append("budget_overrun:max_response_chars")
    if isinstance(raw, Mapping) and raw.get("__provider_error__"):
        errors.append(str(raw["__provider_error__"]))
    if data is not None and not errors:
        errors.extend(_contract_errors(data, packet=packet))
    valid = data is not None and not errors
    selected = _selected_hypothesis(data, packet) if valid else fallback
    abstain = bool(data.get("abstain", False)) if valid and data is not None else False
    if abstain:
        selected = {}
    result: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "case_id": str(packet["case_id"]),
        "status": "valid" if valid else "fail_closed",
        "selection_source": "llm" if valid else "deterministic_fallback",
        "raw_contract_status": "valid" if valid else "invalid",
        "selected_hypothesis_id": str(selected.get("hypothesis_id", "")),
        "selected_service": str(selected.get("service", "")),
        "selected_fault": str(selected.get("fault", "")),
        "evidence_ids": ([] if abstain else list(_sequence(selected.get("supporting_evidence_ids"))) if valid else list(_sequence(fallback.get("supporting_evidence_ids")))),
        "evidence_binding_source": "selected_hypothesis",
        "confidence": 0.0,
        "confidence_status": "not_self_reported",
        "abstain": abstain,
        "validation_errors": list(dict.fromkeys(errors)),
        "action_contract_status": "disabled",
        "executed_actions": [],
        "packet_hash": str(packet["packet_hash"]),
        "model": cfg.model,
        "prompt_schema_version": cfg.prompt_schema_version,
        "decoding_config": dict(cfg.decoding_config),
        "raw_response": raw,
        "raw_response_hash": stable_hash(raw),
        "latency_ms": latency_ms,
    }
    result["result_hash"] = stable_hash({key: value for key, value in result.items() if key not in {"result_hash", "latency_ms"}})
    return result


def _validate_candidate_and_lattice(candidate: Mapping[str, Any], lattice: Mapping[str, Any]) -> None:
    if candidate.get("schema_version") != CANDIDATE_SCHEMA_VERSION:
        raise P114AdjudicationError("invalid_candidate_schema")
    if lattice.get("schema_version") != LATTICE_SCHEMA_VERSION:
        raise P114AdjudicationError("invalid_lattice_schema")
    if str(candidate.get("case_id", "")) != str(lattice.get("case_id", "")):
        raise P114AdjudicationError("case_mismatch")
    if str(lattice.get("lattice_hash", "")) != stable_hash({key: value for key, value in lattice.items() if key != "lattice_hash"}):
        raise P114AdjudicationError("lattice_hash_mismatch")
    candidate_evidence = {str(item.get("node_id", "")) for item in _mapping_sequence(_mapping(candidate.get("evidence_graph")).get("nodes"))}
    lattice_evidence = {str(item) for item in _sequence(lattice.get("evidence_node_ids"))}
    if candidate_evidence != lattice_evidence:
        raise P114AdjudicationError("evidence_set_mismatch")


def _validate_packet(packet: Mapping[str, Any]) -> None:
    if packet.get("schema_version") != PACKET_SCHEMA_VERSION:
        raise P114AdjudicationError("invalid_packet_schema")
    if packet.get("action_contract_status") != "disabled":
        raise P114AdjudicationError("action_authority_enabled")
    if not _mapping_sequence(packet.get("hypotheses")):
        raise P114AdjudicationError("missing_hypotheses")
    hypothesis_ids = {str(item.get("hypothesis_id", "")) for item in _mapping_sequence(packet.get("hypotheses"))}
    if str(packet.get("deterministic_fallback_hypothesis_id", "")) not in hypothesis_ids:
        raise P114AdjudicationError("missing_deterministic_fallback")
    submitted = str(packet.get("packet_hash", ""))
    if not submitted or submitted != stable_hash({key: value for key, value in packet.items() if key != "packet_hash"}):
        raise P114AdjudicationError("packet_hash_mismatch")


def _contract_errors(data: Mapping[str, Any], *, packet: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    keys = {str(key) for key in data}
    errors.extend(f"unknown_output_field:{key}" for key in sorted(keys - _ALLOWED_KEYS))
    abstain = data.get("abstain")
    if not isinstance(abstain, bool):
        errors.append("abstain_not_boolean")
    hypothesis_id = data.get("hypothesis_id")
    if not isinstance(hypothesis_id, str):
        errors.append("hypothesis_id_not_string")
    hypotheses = {str(item.get("hypothesis_id", "")): item for item in _mapping_sequence(packet.get("hypotheses"))}
    if isinstance(hypothesis_id, str) and ((abstain is False and hypothesis_id not in hypotheses) or (abstain is True and hypothesis_id)):
        errors.append("unknown_or_invalid_hypothesis_id")
    if _FORBIDDEN_TEXT.search(json.dumps(data, sort_keys=True, default=str)):
        errors.append("forbidden_action_or_secret_text")
    return errors


def _selected_hypothesis(data: Mapping[str, Any] | None, packet: Mapping[str, Any]) -> Mapping[str, Any]:
    if data is None:
        return {}
    target = str(data.get("hypothesis_id", ""))
    return next((item for item in _mapping_sequence(packet.get("hypotheses")) if item.get("hypothesis_id") == target), {})


def _parse_raw(raw: Mapping[str, Any] | str, errors: list[str]) -> Mapping[str, Any] | None:
    if isinstance(raw, Mapping):
        return raw
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        errors.append("malformed_provider_json")
        return None
    if not isinstance(parsed, Mapping):
        errors.append("provider_json_not_object")
        return None
    return parsed


def _raw_size(raw: Mapping[str, Any] | str) -> int:
    if isinstance(raw, str):
        return len(raw)
    return len(json.dumps(raw, sort_keys=True, default=str))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()


def _mapping_sequence(value: Any) -> tuple[Mapping[str, Any], ...]:
    return tuple(item for item in _sequence(value) if isinstance(item, Mapping))
