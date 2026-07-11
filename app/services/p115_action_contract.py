"""Immutable P115 diagnosis-to-action proposal contract."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p114_hypothesis_lattice import LATTICE_SCHEMA_VERSION

ACTION_PROPOSAL_SCHEMA_VERSION = "p115.action_proposal.v1"
ACTION_AUTHORITY_LEVEL = "L1"
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_TRUTH_BEARING_FIELDS = frozenset(
    {
        "answer",
        "answer_key",
        "expected_action",
        "expected_fault",
        "expected_label",
        "expected_root_cause",
        "fault_type",
        "ground_truth",
        "hidden_outcome",
        "label",
        "oracle",
        "root_cause",
        "root_service",
        "scorer_only_truth",
        "truth",
        "truth_hash",
    }
)
_NORMALIZED_TRUTH_BEARING_FIELDS = frozenset(re.sub(r"[^a-z0-9]+", "", field.casefold()) for field in _TRUTH_BEARING_FIELDS)


class P115ActionContractError(ValueError):
    """Raised when a P115 action proposal crosses the recommendation boundary."""


@dataclass(frozen=True)
class P115ActionProposal:
    schema_version: str
    lattice_hash: str
    hypothesis_id: str
    evidence_ids: tuple[str, ...]
    target: tuple[tuple[str, Any], ...]
    action_pack_hash: str
    expected_utility_inputs: tuple[tuple[str, Any], ...]
    prerequisites: tuple[str, ...]
    contraindications: tuple[str, ...]
    validation_plan: tuple[tuple[str, Any], ...]
    rollback_plan: tuple[tuple[str, Any], ...]
    reversibility: str
    blast_radius: tuple[tuple[str, Any], ...]
    authority_level: str
    executed_actions: tuple[Any, ...]
    proposal_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "lattice_hash": self.lattice_hash,
            "hypothesis_id": self.hypothesis_id,
            "evidence_ids": list(self.evidence_ids),
            "target": _thaw_mapping(self.target),
            "action_pack_hash": self.action_pack_hash,
            "expected_utility_inputs": _thaw_mapping(self.expected_utility_inputs),
            "prerequisites": list(self.prerequisites),
            "contraindications": list(self.contraindications),
            "validation_plan": _thaw_mapping(self.validation_plan),
            "rollback_plan": _thaw_mapping(self.rollback_plan),
            "reversibility": self.reversibility,
            "blast_radius": _thaw_mapping(self.blast_radius),
            "authority_level": self.authority_level,
            "executed_actions": list(self.executed_actions),
            "proposal_hash": self.proposal_hash,
        }


def build_p115_action_proposal(lattice: Mapping[str, Any], proposal: Mapping[str, Any]) -> P115ActionProposal:
    _validate_lattice(lattice)
    _reject_truth_bearing_fields(proposal)
    if proposal.get("authority_level", ACTION_AUTHORITY_LEVEL) != ACTION_AUTHORITY_LEVEL:
        raise P115ActionContractError("action_authority_above_l1")
    if _sequence(proposal.get("executed_actions")):
        raise P115ActionContractError("executed_actions_not_empty")

    lattice_hash = str(lattice["lattice_hash"])
    hypothesis_id = _required_text(proposal, "hypothesis_id")
    hypotheses = {str(item.get("hypothesis_id", "")): item for item in _mapping_sequence(lattice.get("hypotheses"))}
    if hypothesis_id not in hypotheses:
        raise P115ActionContractError("unknown_hypothesis")

    evidence_ids = _text_sequence(proposal.get("evidence_ids"), "missing_evidence_ids")
    lattice_evidence = {str(item) for item in _sequence(lattice.get("evidence_node_ids"))}
    unknown_evidence = sorted(set(evidence_ids) - lattice_evidence)
    if unknown_evidence:
        raise P115ActionContractError(f"unknown_evidence_id:{unknown_evidence[0]}")
    _validate_evidence_bound_to_hypothesis(hypotheses[hypothesis_id], evidence_ids)

    action_pack_hash = _required_hash(proposal, "action_pack_hash", "invalid_action_pack_hash")
    target = _required_mapping(proposal, "target", "missing_target")
    expected_utility_inputs = _required_mapping(proposal, "expected_utility_inputs", "missing_expected_utility_inputs")
    validation_plan = _required_mapping(proposal, "validation_plan", "missing_validation_plan")
    rollback_plan = _required_mapping(proposal, "rollback_plan", "missing_rollback_plan")
    blast_radius = _required_mapping(proposal, "blast_radius", "missing_blast_radius")
    prerequisites = _text_sequence(proposal.get("prerequisites"), "missing_prerequisites")
    contraindications = _text_sequence(proposal.get("contraindications"), "missing_contraindications")
    reversibility = _required_text(proposal, "reversibility")

    payload: dict[str, Any] = {
        "schema_version": ACTION_PROPOSAL_SCHEMA_VERSION,
        "lattice_hash": lattice_hash,
        "hypothesis_id": hypothesis_id,
        "evidence_ids": sorted(dict.fromkeys(evidence_ids)),
        "target": _canonical(target),
        "action_pack_hash": action_pack_hash,
        "expected_utility_inputs": _canonical(expected_utility_inputs),
        "prerequisites": tuple(prerequisites),
        "contraindications": tuple(contraindications),
        "validation_plan": _canonical(validation_plan),
        "rollback_plan": _canonical(rollback_plan),
        "reversibility": reversibility,
        "blast_radius": _canonical(blast_radius),
        "authority_level": ACTION_AUTHORITY_LEVEL,
        "executed_actions": (),
    }
    proposal_hash = stable_hash(_thaw(payload))
    return P115ActionProposal(
        schema_version=ACTION_PROPOSAL_SCHEMA_VERSION,
        lattice_hash=lattice_hash,
        hypothesis_id=hypothesis_id,
        evidence_ids=tuple(payload["evidence_ids"]),
        target=payload["target"],
        action_pack_hash=action_pack_hash,
        expected_utility_inputs=payload["expected_utility_inputs"],
        prerequisites=payload["prerequisites"],
        contraindications=payload["contraindications"],
        validation_plan=payload["validation_plan"],
        rollback_plan=payload["rollback_plan"],
        reversibility=reversibility,
        blast_radius=payload["blast_radius"],
        authority_level=ACTION_AUTHORITY_LEVEL,
        executed_actions=(),
        proposal_hash=proposal_hash,
    )


def _validate_lattice(lattice: Mapping[str, Any]) -> None:
    if lattice.get("schema_version") != LATTICE_SCHEMA_VERSION:
        raise P115ActionContractError("invalid_lattice_schema")
    lattice_hash = str(lattice.get("lattice_hash", ""))
    if not _SHA256_RE.fullmatch(lattice_hash):
        raise P115ActionContractError("invalid_lattice_hash")
    expected = stable_hash({key: value for key, value in lattice.items() if key != "lattice_hash"})
    if lattice_hash != expected:
        raise P115ActionContractError("lattice_hash_mismatch")
    if _sequence(lattice.get("executed_actions")):
        raise P115ActionContractError("lattice_executed_actions_not_empty")


def _reject_truth_bearing_fields(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if _normalize_field_name(str(key)) in _NORMALIZED_TRUTH_BEARING_FIELDS:
                raise P115ActionContractError(f"truth_bearing_field:{key}")
            _reject_truth_bearing_fields(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _reject_truth_bearing_fields(item)


def _validate_evidence_bound_to_hypothesis(hypothesis: Mapping[str, Any], evidence_ids: Sequence[str]) -> None:
    supporting = {str(item) for item in _sequence(hypothesis.get("supporting_evidence_ids"))}
    contradicting = {str(item) for item in _sequence(hypothesis.get("contradicting_evidence_ids"))}
    unbound = sorted(set(evidence_ids) - supporting - contradicting)
    if unbound:
        raise P115ActionContractError(f"evidence_not_bound_to_hypothesis:{unbound[0]}")


def _normalize_field_name(value: str) -> str:
    separated_camel = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return re.sub(r"[^a-z0-9]+", "", separated_camel.casefold())


def _required_hash(data: Mapping[str, Any], key: str, error: str) -> str:
    value = _required_text(data, key)
    if not _SHA256_RE.fullmatch(value):
        raise P115ActionContractError(error)
    return value


def _required_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise P115ActionContractError(f"missing_{key}")
    return value


def _required_mapping(data: Mapping[str, Any], key: str, error: str) -> Mapping[str, Any]:
    value = data.get(key)
    if not isinstance(value, Mapping) or not value:
        raise P115ActionContractError(error)
    return value


def _text_sequence(value: Any, error: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise P115ActionContractError(error)
    normalized = tuple(str(item) for item in value if isinstance(item, str) and item)
    if len(normalized) != len(value):
        raise P115ActionContractError(error)
    return normalized


def _mapping_sequence(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple((str(key), _canonical(item)) for key, item in sorted(value.items(), key=lambda item: str(item[0])))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(_canonical(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if _is_canonical_mapping(value):
        return _thaw_mapping(value)
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _thaw_mapping(value: tuple[tuple[str, Any], ...]) -> dict[str, Any]:
    return {key: _thaw(item) for key, item in value}


def _is_canonical_mapping(value: Any) -> bool:
    return bool(value) and isinstance(value, tuple) and all(
        isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str) for item in value
    )
