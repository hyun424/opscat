"""P117 constrained NVIDIA proposal replay.

The NVIDIA path is parser-only here: raw output is treated as untrusted data and
can never execute, authenticate, mutate, fetch credentials, or override
deterministic eligibility gates.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p117_selector import P117_LABELS

P117_NVIDIA_REPLAY_SCHEMA_VERSION = "p117.nvidia_proposal_replay.v1"
_ALLOWED_FIELDS = frozenset(
    {
        "selected_label",
        "selected_action_pack_id",
        "ranked_action_pack_ids",
        "cited_evidence_ids",
        "expected_utility",
        "utility_interval",
        "calibrated_confidence",
        "abstention_reason",
        "rationale",
    }
)
_FORBIDDEN_AUTHORITY_TEXT = re.compile(
    r"\b("
    r"kubectl|helm|terraform|ansible|ssh|scp|sudo|bash|sh\s+-c|rm\s+-rf|"
    r"aws|gcloud|az\s+|credential|credentials|secret|token|password|api[_-]?key|"
    r"delete|drop\s+table|truncate|insert\s+into|update\s+\w+\s+set|"
    r"production|prod|mutate|mutation|target\s+selector|restart|exec|subprocess|shell"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class P117NvidiaProposalReplay:
    payload: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        thawed = _thaw(self.payload)
        if not isinstance(thawed, dict):
            raise ValueError("invalid_replay_payload")
        return thawed


def replay_p117_nvidia_proposal(
    episode: Mapping[str, Any],
    raw: Mapping[str, Any] | Sequence[Any] | str,
    *,
    deterministic_decision: Mapping[str, Any],
) -> P117NvidiaProposalReplay:
    errors: list[str] = []
    data = _parse_raw(raw, errors)
    allowed_action_ids = {str(pack.get("action_pack_id", "")) for pack in _mapping_tuple(episode.get("p115_signed_action_pack_refs"))}
    visible_evidence_ids = {str(item) for item in _sequence(episode.get("visible_evidence_ids"))}
    if data is not None and not errors:
        errors.extend(_contract_errors(data, allowed_action_ids=allowed_action_ids, visible_evidence_ids=visible_evidence_ids))
    if data is not None and not errors:
        errors.extend(_deterministic_gate_errors(data, deterministic_decision))
    valid = data is not None and not errors
    proposal = _proposal_payload(data) if valid and data is not None else None
    final_decision = proposal if proposal is not None else dict(deterministic_decision)
    payload: dict[str, Any] = {
        "schema_version": P117_NVIDIA_REPLAY_SCHEMA_VERSION,
        "decision_episode_id": str(episode.get("decision_episode_id", "")),
        "status": "valid" if valid else "fail_closed",
        "selection_source": "nvidia_proposal" if valid else "deterministic_fallback",
        "raw_contract_status": "valid" if valid else "invalid",
        "validation_errors": list(dict.fromkeys(errors)),
        "fallback_reason": None if valid else (errors[0] if errors else "invalid_provider_output"),
        "proposal": proposal,
        "final_decision": final_decision,
        "disagreement_with_deterministic": bool(proposal is not None and _decision_key(proposal) != _decision_key(deterministic_decision)),
        "raw_response": raw,
        "raw_response_hash": stable_hash(raw),
        "execution_authority": "none",
        "llm_authority": "proposal_only",
        "production_authority": False,
        "credential_scope": False,
        "p118_required_for_execution": True,
    }
    payload["replay_hash"] = stable_hash({key: value for key, value in payload.items() if key != "replay_hash"})
    return P117NvidiaProposalReplay(payload=_freeze(payload))


def _contract_errors(data: Mapping[str, Any], *, allowed_action_ids: set[str], visible_evidence_ids: set[str]) -> list[str]:
    errors: list[str] = []
    keys = {str(key) for key in data}
    errors.extend(f"unknown_output_field:{key}" for key in sorted(keys - _ALLOWED_FIELDS))
    label = data.get("selected_label")
    if not isinstance(label, str) or label not in P117_LABELS:
        errors.append("unknown_selected_label")
    selected_action_pack_id = data.get("selected_action_pack_id")
    ranked_ids = _text_tuple(data.get("ranked_action_pack_ids"))
    cited_ids = _text_tuple(data.get("cited_evidence_ids"))
    if not cited_ids:
        errors.append("missing_cited_evidence_ids")
    unknown_ranked = sorted(set(ranked_ids) - allowed_action_ids)
    if unknown_ranked:
        errors.append(f"unknown_action_pack_id:{unknown_ranked[0]}")
    if label == "act":
        if not isinstance(selected_action_pack_id, str) or selected_action_pack_id not in allowed_action_ids:
            errors.append("unknown_action_pack_id")
    elif selected_action_pack_id is not None:
        errors.append("selected_action_pack_id_for_non_act_label")
    invented_evidence = sorted(set(cited_ids) - visible_evidence_ids)
    if invented_evidence:
        errors.append(f"invented_evidence_id:{invented_evidence[0]}")
    if "utility_interval" in data:
        _validate_interval(data.get("utility_interval"), errors)
    if _contains_forbidden_text(data):
        errors.append("forbidden_authority_text")
    return errors


def _proposal_payload(data: Mapping[str, Any]) -> dict[str, Any]:
    selected_label = str(data["selected_label"])
    raw_interval = data.get("utility_interval")
    utility_interval = list(raw_interval) if isinstance(raw_interval, Sequence) and not isinstance(raw_interval, (str, bytes)) else None
    return {
        "selected_label": selected_label,
        "selected_action_pack_id": data.get("selected_action_pack_id") if selected_label == "act" else None,
        "ranked_action_pack_ids": list(_text_tuple(data.get("ranked_action_pack_ids"))),
        "cited_evidence_ids": list(_text_tuple(data.get("cited_evidence_ids"))),
        "expected_utility": data.get("expected_utility"),
        "utility_interval": utility_interval,
        "calibrated_confidence": data.get("calibrated_confidence"),
        "abstention_reason": data.get("abstention_reason"),
        "execution_authority": "none",
        "llm_authority": "proposal_only",
        "production_authority": False,
        "credential_scope": False,
        "p118_required_for_execution": True,
    }


def _deterministic_gate_errors(proposal: Mapping[str, Any], deterministic: Mapping[str, Any]) -> list[str]:
    """Prevent model prose from turning a deterministic non-action into action."""

    proposal_label = proposal.get("selected_label")
    deterministic_label = deterministic.get("selected_label")
    if proposal_label == "act" and deterministic_label != "act":
        return ["deterministic_safety_gate_override"]
    if proposal_label == "act" and proposal.get("selected_action_pack_id") != deterministic.get("selected_action_pack_id"):
        return ["deterministic_action_eligibility_override"]
    return []


def _parse_raw(raw: Mapping[str, Any] | Sequence[Any] | str, errors: list[str]) -> Mapping[str, Any] | None:
    if isinstance(raw, Mapping):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            errors.append("malformed_provider_json")
            return None
        if not isinstance(parsed, Mapping):
            errors.append("provider_json_not_object")
            return None
        return parsed
    errors.append("provider_json_not_object")
    return None


def _validate_interval(value: Any, errors: list[str]) -> None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2:
        errors.append("invalid_utility_interval")
        return
    try:
        lower = float(value[0])
        upper = float(value[1])
    except (TypeError, ValueError):
        errors.append("invalid_utility_interval")
        return
    if lower > upper:
        errors.append("invalid_utility_interval")


def _decision_key(decision: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        decision.get("selected_label"),
        decision.get("selected_action_pack_id"),
        tuple(_sequence(decision.get("ranked_action_pack_ids"))),
    )


def _contains_forbidden_text(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_forbidden_text(key) or _contains_forbidden_text(item) for key, item in value.items())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_forbidden_text(item) for item in value)
    return isinstance(value, str) and bool(_FORBIDDEN_AUTHORITY_TEXT.search(value))


def _text_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str) and item)


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()


def _mapping_tuple(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple((str(key), _freeze(item)) for key, item in sorted(value.items(), key=lambda item: str(item[0])))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if _is_frozen_mapping(value):
        return {key: _thaw(item) for key, item in value}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_thaw(item) for item in value]
    return value


def _is_frozen_mapping(value: Any) -> bool:
    return bool(value) and isinstance(value, tuple) and all(isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str) for item in value)
