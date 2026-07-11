"""Immutable P117 evidence-bound decision episode and output contracts."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p117_evidence_acquisition import FROZEN_EVIDENCE_TAXONOMY

P117_DECISION_EPISODE_SCHEMA_VERSION = "p117.decision_episode.v1"
P117_DECISION_OUTPUT_SCHEMA_VERSION = "p117.decision_output.v1"
P117_LABELS = frozenset({"act", "investigate_more", "no_action", "escalate", "abstain"})
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_EVIDENCE_CLASS_IDS = frozenset(item.class_id for item in FROZEN_EVIDENCE_TAXONOMY)
_VISIBLE_EVIDENCE_PREFIXES = tuple(f"ev-{class_id}-" for class_id in _EVIDENCE_CLASS_IDS)
_FORBIDDEN_FIELDS = frozenset(
    {
        "answer",
        "answerkey",
        "blindlabel",
        "credential",
        "credentials",
        "groundtruth",
        "hiddenlabel",
        "hiddenoutcome",
        "label",
        "oracle",
        "p114actiontext",
        "password",
        "privatechainofthought",
        "providerprivatereasoning",
        "rootcause",
        "scoreronlytruth",
        "secret",
        "targetselector",
        "truth",
        "unsealedlabel",
    }
)
_FORBIDDEN_TEXT_RE = re.compile(
    r"(kubectl|curl|ssh|aws\s|gcloud\s|terraform\s+apply|drop\s+database|delete\s+pod|restart\s+production|http://|https://|postgres://|mysql://|password|secret|credential)",
    re.IGNORECASE,
)
_AUTHORITY_COUNTERS = (
    "auth",
    "credentials",
    "executor",
    "subprocess",
    "kubernetes",
    "cloud",
    "database_mutation",
    "production_adapter",
    "network_mutation",
    "online_policy_write",
    "production_mutation",
)


class P117ContractError(ValueError):
    """Raised when a P117 artifact violates the evidence-bound contract."""


@dataclass(frozen=True)
class P117DecisionEpisode:
    schema_version: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", _freeze(self.payload))

    def to_dict(self) -> dict[str, Any]:
        thawed = _thaw(self.payload)
        if not isinstance(thawed, dict):
            raise P117ContractError("invalid_episode_payload")
        return thawed


@dataclass(frozen=True)
class P117DecisionOutput:
    schema_version: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", _freeze(self.payload))

    def to_dict(self) -> dict[str, Any]:
        thawed = _thaw(self.payload)
        if not isinstance(thawed, dict):
            raise P117ContractError("invalid_output_payload")
        return thawed


def build_p117_decision_episode(data: Mapping[str, Any]) -> P117DecisionEpisode:
    _validate_schema(data, P117_DECISION_EPISODE_SCHEMA_VERSION)
    _reject_forbidden(data)
    visible_evidence_ids = _required_text_list(data, "visible_evidence_ids")
    if any(not item.startswith(_VISIBLE_EVIDENCE_PREFIXES) for item in visible_evidence_ids):
        raise P117ContractError("invented_visible_evidence_id")
    action_pack_refs = _action_pack_refs(data.get("p115_signed_action_pack_refs"))
    payload: dict[str, Any] = {
        "schema_version": P117_DECISION_EPISODE_SCHEMA_VERSION,
        "decision_episode_id": _required_text(data, "decision_episode_id"),
        "p114_lattice_ref": _artifact_ref(data.get("p114_lattice_ref"), "p114_lattice_ref", require_sealed=True),
        "p114_selected_hypothesis_or_abstention": _required_text(data, "p114_selected_hypothesis_or_abstention"),
        "visible_evidence_ids": sorted(visible_evidence_ids),
        "missing_evidence_markers": sorted(
            _text_list(data.get("missing_evidence_markers"), allow_empty=True, error="invalid_missing_evidence_markers")
        ),
        "p115_case_ref": _artifact_ref(data.get("p115_case_ref"), "p115_case_ref"),
        "p115_signed_action_pack_refs": action_pack_refs,
        "action_pack_ids": [str(item["action_pack_id"]) for item in action_pack_refs],
        "p116_measured_outcome_refs": _outcome_refs(data.get("p116_measured_outcome_refs")),
        "calibration_profile_ref": _artifact_ref(data.get("calibration_profile_ref"), "calibration_profile_ref"),
        "utility_profile_ref": _artifact_ref(data.get("utility_profile_ref"), "utility_profile_ref"),
        "evaluation_split": _required_text(data, "evaluation_split"),
        "frozen_seed": _required_int(data, "frozen_seed"),
        "authority_boundary_receipt": _authority_receipt(data.get("authority_boundary_receipt")),
    }
    payload["episode_hash"] = stable_hash(payload)
    return P117DecisionEpisode(P117_DECISION_EPISODE_SCHEMA_VERSION, payload)


def build_p117_decision_output(episode: P117DecisionEpisode, data: Mapping[str, Any]) -> P117DecisionOutput:
    episode_payload = episode.to_dict()
    _validate_schema(data, P117_DECISION_OUTPUT_SCHEMA_VERSION)
    _reject_forbidden(data)
    selected_label = _required_text(data, "selected_label")
    if selected_label not in P117_LABELS:
        raise P117ContractError(f"unknown_selected_label:{selected_label}")
    known_actions = set(_required_text_list(episode_payload, "action_pack_ids"))
    selected_action = data.get("selected_action_pack_id")
    if selected_label == "act":
        if not isinstance(selected_action, str) or not selected_action:
            raise P117ContractError("act_requires_action_pack")
        if selected_action not in known_actions:
            raise P117ContractError(f"unknown_action_pack_id:{selected_action}")
    elif selected_action is not None:
        raise P117ContractError("non_action_has_action_pack")
    ranked_action_ids = _text_list(data.get("ranked_action_pack_ids"), allow_empty=True, error="invalid_ranked_action_pack_ids")
    unknown_ranked = sorted(set(ranked_action_ids) - known_actions)
    if unknown_ranked:
        raise P117ContractError(f"unknown_action_pack_id:{unknown_ranked[0]}")
    cited_evidence_ids = _text_list(data.get("cited_evidence_ids"), allow_empty=False, error="missing_cited_evidence_ids")
    visible = set(_required_text_list(episode_payload, "visible_evidence_ids"))
    unknown_evidence = sorted(set(cited_evidence_ids) - visible)
    if unknown_evidence:
        raise P117ContractError(f"invented_evidence_id:{unknown_evidence[0]}")
    requests = _requested_evidence_classes(data.get("requested_evidence_classes"), set(_required_text_list(episode_payload, "missing_evidence_markers")))
    utility_interval = _utility_interval(data.get("utility_interval")) if data.get("utility_interval") is not None else None
    if selected_label == "act" and utility_interval is None:
        raise P117ContractError("act_requires_utility_interval")
    confidence = data.get("calibrated_confidence")
    if not isinstance(confidence, int | float) or isinstance(confidence, bool) or not 0 <= float(confidence) <= 1:
        raise P117ContractError("invalid_calibrated_confidence")
    receipt = _authority_receipt(data.get("authority_boundary_receipt"))
    payload: dict[str, Any] = {
        "schema_version": P117_DECISION_OUTPUT_SCHEMA_VERSION,
        "decision_episode_id": episode_payload["decision_episode_id"],
        "episode_hash": episode_payload["episode_hash"],
        "selected_label": selected_label,
        "selected_action_pack_id": selected_action,
        "ranked_action_pack_ids": ranked_action_ids,
        "requested_evidence_classes": requests,
        "cited_evidence_ids": sorted(cited_evidence_ids),
        "contradiction_set_ids": _text_list(data.get("contradiction_set_ids"), allow_empty=True, error="invalid_contradiction_set_ids"),
        "expected_utility": _nullable_number(data.get("expected_utility"), "expected_utility"),
        "utility_interval": [utility_interval[0], utility_interval[1]] if utility_interval is not None else None,
        "calibrated_confidence": float(confidence),
        "abstention_reason": _nullable_text(data.get("abstention_reason"), "abstention_reason"),
        "fallback_reason": _nullable_text(data.get("fallback_reason"), "fallback_reason"),
        "llm_proposal_receipt": _nullable_mapping(data.get("llm_proposal_receipt"), "llm_proposal_receipt"),
        "authority_boundary_receipt": receipt,
        "execution_authority": "none",
        "llm_authority": "proposal_only",
        "production_authority": False,
        "credential_scope": False,
        "p118_required_for_execution": True,
    }
    payload["output_hash"] = stable_hash(payload)
    return P117DecisionOutput(P117_DECISION_OUTPUT_SCHEMA_VERSION, payload)


def _validate_schema(data: Mapping[str, Any], expected: str) -> None:
    if data.get("schema_version") != expected:
        raise P117ContractError(f"unsupported_schema_version:{data.get('schema_version')}")


def _artifact_ref(value: Any, field: str, *, require_sealed: bool = False) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise P117ContractError(f"missing_{field}")
    _reject_forbidden(value)
    artifact_hash = value.get("artifact_hash")
    if not isinstance(artifact_hash, str) or not _SHA256_RE.fullmatch(artifact_hash):
        raise P117ContractError(f"invalid_{field}_hash")
    if require_sealed:
        if value.get("sealed") is not True:
            raise P117ContractError("unsealed_lattice_ref")
        replay_hash = value.get("replay_receipt_hash")
        if not isinstance(replay_hash, str) or not _SHA256_RE.fullmatch(replay_hash):
            raise P117ContractError("missing_p114_replay_receipt")
    return _plain_mapping(value)


def _action_pack_refs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or not value:
        raise P117ContractError("missing_p115_signed_action_pack_refs")
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping):
            raise P117ContractError("invalid_action_pack_ref")
        _reject_forbidden(item)
        action_id = _required_text(item, "action_pack_id")
        if action_id in seen:
            raise P117ContractError(f"duplicate_action_pack_id:{action_id}")
        seen.add(action_id)
        for hash_key, error in (("pack_hash", "invalid_pack_hash"), ("signature", "invalid_signature")):
            hash_value = item.get(hash_key)
            if not isinstance(hash_value, str) or not _SHA256_RE.fullmatch(hash_value):
                raise P117ContractError(error)
        refs.append(
            {
                "action_pack_id": action_id,
                "pack_hash": str(item["pack_hash"]),
                "signature": str(item["signature"]),
                "signer_key_id": _required_text(item, "signer_key_id"),
            }
        )
    return sorted(refs, key=lambda item: item["action_pack_id"])


def _outcome_refs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or not value:
        raise P117ContractError("missing_p116_measured_outcome_refs")
    refs: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise P117ContractError("invalid_p116_outcome_ref")
        _reject_forbidden(item)
        record_hash = item.get("record_hash")
        if not isinstance(record_hash, str) or not _SHA256_RE.fullmatch(record_hash):
            raise P117ContractError("invalid_p116_record_hash")
        refs.append(_plain_mapping(item))
    return sorted(refs, key=lambda item: str(item.get("outcome_id", item.get("record_hash", ""))))


def _authority_receipt(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise P117ContractError("missing_authority_boundary_receipt")
    if value.get("execution_authority") != "none":
        raise P117ContractError("execution_authority_not_none")
    if value.get("llm_authority") != "proposal_only":
        raise P117ContractError("llm_authority_not_proposal_only")
    for key, expected in (("production_authority", False), ("credential_scope", False), ("p118_required_for_execution", True)):
        if value.get(key) is not expected:
            raise P117ContractError(f"invalid_authority_{key}")
    counters = value.get("counters")
    if not isinstance(counters, Mapping):
        raise P117ContractError("missing_authority_counters")
    normalized_counters: dict[str, int] = {}
    for key in _AUTHORITY_COUNTERS:
        counter = counters.get(key)
        if not isinstance(counter, int) or isinstance(counter, bool):
            raise P117ContractError(f"missing_authority_counter:{key}")
        if counter != 0:
            raise P117ContractError(f"authority_counter_nonzero:{key}")
        normalized_counters[key] = 0
    return {
        "execution_authority": "none",
        "llm_authority": "proposal_only",
        "production_authority": False,
        "credential_scope": False,
        "p118_required_for_execution": True,
        "counters": normalized_counters,
    }


def _requested_evidence_classes(value: Any, missing_markers: set[str]) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise P117ContractError("invalid_requested_evidence_classes")
    requests: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise P117ContractError("invalid_requested_evidence_class")
        class_id = _required_text(item, "class_id")
        if class_id not in _EVIDENCE_CLASS_IDS:
            raise P117ContractError(f"unknown_evidence_class:{class_id}")
        marker = _required_text(item, "missing_evidence_marker")
        if marker not in missing_markers:
            raise P117ContractError(f"unknown_missing_evidence_marker:{marker}")
        requests.append({"class_id": class_id, "missing_evidence_marker": marker})
    return sorted(requests, key=lambda item: (item["missing_evidence_marker"], item["class_id"]))


def _reject_forbidden(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if _normalized_field(key) in _FORBIDDEN_FIELDS and not (str(key) == "credentials" and isinstance(item, int) and not isinstance(item, bool)):
                raise P117ContractError(f"forbidden_field:{key}")
            _reject_forbidden(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _reject_forbidden(item)
    elif isinstance(value, str) and _FORBIDDEN_TEXT_RE.search(value):
        raise P117ContractError("forbidden_text")


def _plain_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _plain_value(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}


def _plain_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _plain_mapping(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_plain_value(item) for item in value]
    return value


def _normalized_field(value: Any) -> str:
    separated = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(value))
    return re.sub(r"[^a-z0-9]+", "", separated.casefold())


def _required_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise P117ContractError(f"missing_{key}")
    return value.strip()


def _nullable_text(value: Any, key: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise P117ContractError(f"invalid_{key}")
    _reject_forbidden(value)
    return value.strip()


def _nullable_mapping(value: Any, key: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise P117ContractError(f"invalid_{key}")
    _reject_forbidden(value)
    return _plain_mapping(value)


def _nullable_number(value: Any, key: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise P117ContractError(f"invalid_{key}")
    return float(value)


def _required_int(data: Mapping[str, Any], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise P117ContractError(f"missing_{key}")
    return value


def _required_text_list(data: Mapping[str, Any], key: str) -> list[str]:
    return _text_list(data.get(key), allow_empty=False, error=f"missing_{key}")


def _text_list(value: Any, *, allow_empty: bool, error: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise P117ContractError(error)
    result = [item for item in value if isinstance(item, str) and item]
    if len(result) != len(value) or len(result) != len(set(result)) or (not allow_empty and not result):
        raise P117ContractError(error)
    for item in result:
        _reject_forbidden(item)
    return sorted(result)


def _utility_interval(value: Any) -> tuple[float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or len(value) != 2:
        raise P117ContractError("invalid_utility_interval")
    low, high = value
    if not isinstance(low, int | float) or isinstance(low, bool) or not isinstance(high, int | float) or isinstance(high, bool):
        raise P117ContractError("invalid_utility_interval")
    if float(low) > float(high):
        raise P117ContractError("invalid_utility_interval")
    return (float(low), float(high))


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value
