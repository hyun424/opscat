"""P117 deterministic evidence-bound action selector.

This module is intentionally offline and Mapping-friendly.  It consumes frozen
benchmark metadata and emits recommendation-only decisions; it never executes,
authenticates, mutates, or calls provider APIs.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.services.p110_evaluation import stable_hash

P117_EPISODE_SCHEMA_VERSION = "p117.decision_episode.v1"
P117_DECISION_SCHEMA_VERSION = "p117.deterministic_decision.v1"
P117_LABELS = frozenset({"act", "investigate_more", "no_action", "escalate", "abstain"})

_FORBIDDEN_AUTHORITY_TEXT = re.compile(
    r"\b("
    r"kubectl|helm|terraform|ansible|ssh|scp|sudo|bash|sh\s+-c|rm\s+-rf|"
    r"aws|gcloud|az\s+|credential|credentials|secret|token|password|api[_-]?key|"
    r"delete|drop\s+table|truncate|insert\s+into|update\s+\w+\s+set|"
    r"production|prod|mutate|mutation|restart|exec|subprocess|shell"
    r")\b",
    re.IGNORECASE,
)


class P117SelectorError(ValueError):
    """Raised when a P117 decision episode cannot be safely selected."""


@dataclass(frozen=True)
class P117DeterministicDecision:
    schema_version: str
    decision_episode_id: str
    selected_label: str
    selected_action_pack_id: str | None
    ranked_action_pack_ids: tuple[str, ...]
    requested_evidence_classes: tuple[str, ...]
    cited_evidence_ids: tuple[str, ...]
    contradiction_set_ids: tuple[str, ...]
    expected_utility: float | None
    utility_interval: tuple[float, float] | None
    calibrated_confidence: float
    abstention_reason: str | None
    deterministic_fallback_reason: str | None
    llm_proposal_receipt: Mapping[str, Any] | None
    authority_boundary_receipt: Mapping[str, Any]
    execution_authority: str
    llm_authority: str
    production_authority: bool
    credential_scope: bool
    p118_required_for_execution: bool
    decision_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision_episode_id": self.decision_episode_id,
            "selected_label": self.selected_label,
            "selected_action_pack_id": self.selected_action_pack_id,
            "ranked_action_pack_ids": list(self.ranked_action_pack_ids),
            "requested_evidence_classes": list(self.requested_evidence_classes),
            "cited_evidence_ids": list(self.cited_evidence_ids),
            "contradiction_set_ids": list(self.contradiction_set_ids),
            "expected_utility": self.expected_utility,
            "utility_interval": list(self.utility_interval) if self.utility_interval is not None else None,
            "calibrated_confidence": self.calibrated_confidence,
            "abstention_reason": self.abstention_reason,
            "deterministic_fallback_reason": self.deterministic_fallback_reason,
            "llm_proposal_receipt": dict(self.llm_proposal_receipt) if self.llm_proposal_receipt is not None else None,
            "authority_boundary_receipt": _thaw(self.authority_boundary_receipt),
            "execution_authority": self.execution_authority,
            "llm_authority": self.llm_authority,
            "production_authority": self.production_authority,
            "credential_scope": self.credential_scope,
            "p118_required_for_execution": self.p118_required_for_execution,
            "decision_hash": self.decision_hash,
        }


def select_p117_decision(episode: Mapping[str, Any]) -> P117DeterministicDecision:
    """Select a deterministic P117 decision from a frozen benchmark episode."""

    _validate_episode_shell(episode)
    visible_evidence_ids = _text_tuple(episode.get("visible_evidence_ids"), "missing_visible_evidence_ids")
    action_packs = _mapping_tuple(episode.get("p115_signed_action_pack_refs"))
    outcomes = _mapping_tuple(episode.get("p116_measured_outcome_refs"))
    if not action_packs:
        raise P117SelectorError("missing_action_packs")
    if not outcomes:
        raise P117SelectorError("missing_p116_outcomes")
    _validate_action_packs(action_packs)
    _validate_outcome_binding(action_packs, outcomes)
    _validate_outcomes(outcomes)

    confidence, threshold = _calibration(episode)
    ranked = _ranked_action_pack_ids(action_packs, outcomes)
    contradiction_ids = _text_tuple(episode.get("contradiction_set_ids", ()), "invalid_contradiction_set_ids", allow_empty=True)
    authority_receipt = _mapping(episode.get("authority_boundary_receipt"))
    if _has_nonzero_authority(authority_receipt):
        return _fallback_decision(
            episode,
            selected_label="abstain",
            ranked_action_pack_ids=ranked,
            calibrated_confidence=confidence,
            reason="authority_boundary_nonzero",
            abstention_reason="authority_boundary_nonzero",
            contradiction_set_ids=contradiction_ids,
        )

    if episode.get("human_authorization_required") is True:
        return _fallback_decision(
            episode,
            selected_label="escalate",
            ranked_action_pack_ids=ranked,
            calibrated_confidence=confidence,
            reason="human_authorization_required",
            abstention_reason="human_authorization_required",
            contradiction_set_ids=contradiction_ids,
        )

    missing_markers = _text_tuple(episode.get("missing_evidence_markers", ()), "invalid_missing_evidence_markers", allow_empty=True)
    if missing_markers:
        return _fallback_decision(
            episode,
            selected_label="investigate_more",
            ranked_action_pack_ids=ranked,
            calibrated_confidence=confidence,
            reason="missing_required_evidence",
            requested_evidence_classes=missing_markers,
            contradiction_set_ids=contradiction_ids,
        )

    visible_set = set(visible_evidence_ids)
    if any(visible_set.intersection(_text_tuple(pack.get("contraindication_evidence_ids", ()), "invalid_contraindications", allow_empty=True)) for pack in action_packs):
        return _fallback_decision(
            episode,
            selected_label="abstain",
            ranked_action_pack_ids=ranked,
            calibrated_confidence=confidence,
            reason="contraindication_present",
            abstention_reason="contraindication_present",
            contradiction_set_ids=contradiction_ids,
        )
    if confidence < threshold:
        return _fallback_decision(
            episode,
            selected_label="abstain",
            ranked_action_pack_ids=ranked,
            calibrated_confidence=confidence,
            reason="calibration_below_threshold",
            abstention_reason="calibration_below_threshold",
            contradiction_set_ids=contradiction_ids,
        )
    if any(outcome.get("measurement_status") != "comparable" or outcome.get("controls_comparable") is not True for outcome in outcomes):
        return _fallback_decision(
            episode,
            selected_label="no_action",
            ranked_action_pack_ids=ranked,
            calibrated_confidence=confidence,
            reason="outcome_not_comparable",
            contradiction_set_ids=contradiction_ids,
        )
    if any(bool(outcome.get("natural_recovery_dominates")) for outcome in outcomes):
        return _fallback_decision(
            episode,
            selected_label="no_action",
            ranked_action_pack_ids=ranked,
            calibrated_confidence=confidence,
            reason="natural_recovery_dominates",
            contradiction_set_ids=contradiction_ids,
        )
    if any(_interval(outcome)[0] <= 0.0 <= _interval(outcome)[1] for outcome in outcomes):
        return _fallback_decision(
            episode,
            selected_label="no_action",
            ranked_action_pack_ids=ranked,
            calibrated_confidence=confidence,
            reason="utility_interval_crosses_zero",
            contradiction_set_ids=contradiction_ids,
        )

    outcome_by_id = {str(outcome["action_pack_id"]): outcome for outcome in outcomes}
    eligible = [pack for pack in action_packs if set(_text_tuple(pack.get("required_evidence_ids", ()), "invalid_required_evidence_ids", allow_empty=True)).issubset(visible_set)]
    if not eligible:
        return _fallback_decision(
            episode,
            selected_label="investigate_more",
            ranked_action_pack_ids=ranked,
            calibrated_confidence=confidence,
            reason="missing_required_evidence",
            requested_evidence_classes=_required_evidence_classes(action_packs),
            contradiction_set_ids=contradiction_ids,
        )
    selected = min(eligible, key=lambda pack: ranked.index(str(pack["action_pack_id"])))
    selected_id = str(selected["action_pack_id"])
    selected_outcome = outcome_by_id[selected_id]
    expected_utility = round(float(selected_outcome["utility_delta"]), 6)
    if expected_utility <= float(_mapping(episode.get("utility_profile_ref")).get("utility_threshold", 0.0)):
        return _fallback_decision(
            episode,
            selected_label="no_action",
            ranked_action_pack_ids=ranked,
            calibrated_confidence=confidence,
            reason="nonpositive_expected_utility",
            contradiction_set_ids=contradiction_ids,
        )
    required_ids = _text_tuple(selected.get("required_evidence_ids", ()), "invalid_required_evidence_ids", allow_empty=True)
    cited = tuple(item for item in visible_evidence_ids if item in set(required_ids))
    interval = _interval(selected_outcome)
    return _build_decision(
        decision_episode_id=str(episode["decision_episode_id"]),
        selected_label="act",
        selected_action_pack_id=selected_id,
        ranked_action_pack_ids=ranked,
        requested_evidence_classes=(),
        cited_evidence_ids=cited,
        contradiction_set_ids=contradiction_ids,
        expected_utility=expected_utility,
        utility_interval=interval,
        calibrated_confidence=round(confidence, 6),
        abstention_reason=None,
        deterministic_fallback_reason=None,
        llm_proposal_receipt=None,
        authority_boundary_receipt=authority_receipt,
    )


def _build_decision(
    *,
    decision_episode_id: str,
    selected_label: str,
    selected_action_pack_id: str | None,
    ranked_action_pack_ids: tuple[str, ...],
    requested_evidence_classes: tuple[str, ...],
    cited_evidence_ids: tuple[str, ...],
    contradiction_set_ids: tuple[str, ...],
    expected_utility: float | None,
    utility_interval: tuple[float, float] | None,
    calibrated_confidence: float,
    abstention_reason: str | None,
    deterministic_fallback_reason: str | None,
    llm_proposal_receipt: Mapping[str, Any] | None,
    authority_boundary_receipt: Mapping[str, Any],
) -> P117DeterministicDecision:
    base: dict[str, Any] = {
        "schema_version": P117_DECISION_SCHEMA_VERSION,
        "decision_episode_id": decision_episode_id,
        "selected_label": selected_label,
        "selected_action_pack_id": selected_action_pack_id,
        "ranked_action_pack_ids": list(ranked_action_pack_ids),
        "requested_evidence_classes": list(requested_evidence_classes),
        "cited_evidence_ids": list(cited_evidence_ids),
        "contradiction_set_ids": list(contradiction_set_ids),
        "expected_utility": expected_utility,
        "utility_interval": list(utility_interval) if utility_interval is not None else None,
        "calibrated_confidence": calibrated_confidence,
        "abstention_reason": abstention_reason,
        "deterministic_fallback_reason": deterministic_fallback_reason,
        "llm_proposal_receipt": dict(llm_proposal_receipt) if llm_proposal_receipt is not None else None,
        "authority_boundary_receipt": _thaw(authority_boundary_receipt),
        "execution_authority": "none",
        "llm_authority": "proposal_only",
        "production_authority": False,
        "credential_scope": False,
        "p118_required_for_execution": True,
    }
    decision_hash = stable_hash(base)
    return P117DeterministicDecision(
        schema_version=P117_DECISION_SCHEMA_VERSION,
        decision_episode_id=decision_episode_id,
        selected_label=selected_label,
        selected_action_pack_id=selected_action_pack_id,
        ranked_action_pack_ids=ranked_action_pack_ids,
        requested_evidence_classes=requested_evidence_classes,
        cited_evidence_ids=cited_evidence_ids,
        contradiction_set_ids=contradiction_set_ids,
        expected_utility=expected_utility,
        utility_interval=utility_interval,
        calibrated_confidence=calibrated_confidence,
        abstention_reason=abstention_reason,
        deterministic_fallback_reason=deterministic_fallback_reason,
        llm_proposal_receipt=llm_proposal_receipt,
        authority_boundary_receipt=_freeze(authority_boundary_receipt),
        execution_authority="none",
        llm_authority="proposal_only",
        production_authority=False,
        credential_scope=False,
        p118_required_for_execution=True,
        decision_hash=decision_hash,
    )


def _fallback_decision(
    episode: Mapping[str, Any],
    *,
    selected_label: str,
    ranked_action_pack_ids: tuple[str, ...],
    calibrated_confidence: float,
    reason: str,
    abstention_reason: str | None = None,
    requested_evidence_classes: Sequence[str] = (),
    contradiction_set_ids: Sequence[str] = (),
) -> P117DeterministicDecision:
    return _build_decision(
        decision_episode_id=str(episode["decision_episode_id"]),
        selected_label=selected_label,
        selected_action_pack_id=None,
        ranked_action_pack_ids=ranked_action_pack_ids,
        requested_evidence_classes=tuple(dict.fromkeys(str(item) for item in requested_evidence_classes)),
        cited_evidence_ids=_text_tuple(episode.get("visible_evidence_ids"), "missing_visible_evidence_ids"),
        contradiction_set_ids=tuple(str(item) for item in contradiction_set_ids),
        expected_utility=None,
        utility_interval=None,
        calibrated_confidence=round(calibrated_confidence, 6),
        abstention_reason=abstention_reason,
        deterministic_fallback_reason=reason,
        llm_proposal_receipt=None,
        authority_boundary_receipt=_mapping(episode.get("authority_boundary_receipt")),
    )


def _validate_episode_shell(episode: Mapping[str, Any]) -> None:
    if episode.get("schema_version") != P117_EPISODE_SCHEMA_VERSION:
        raise P117SelectorError("invalid_episode_schema")
    required_keys = (
        "decision_episode_id",
        "visible_evidence_ids",
        "missing_evidence_markers",
        "p115_signed_action_pack_refs",
        "p116_measured_outcome_refs",
        "calibration_profile_ref",
        "utility_profile_ref",
        "evaluation_split",
        "frozen_seed",
        "authority_boundary_receipt",
    )
    for key in required_keys:
        if key not in episode:
            raise P117SelectorError(f"missing_{key}")
    if not isinstance(episode.get("decision_episode_id"), str) or not episode.get("decision_episode_id"):
        raise P117SelectorError("missing_decision_episode_id")
    if _contains_forbidden_text(episode):
        raise P117SelectorError("forbidden_authority_text")


def _validate_action_packs(action_packs: Sequence[Mapping[str, Any]]) -> None:
    seen: set[str] = set()
    for pack in action_packs:
        action_id = _required_text(pack, "action_pack_id")
        if action_id in seen:
            raise P117SelectorError("duplicate_action_pack_id")
        seen.add(action_id)
        if pack.get("signed") is not True:
            raise P117SelectorError("unsigned_action_pack")
        if pack.get("executor_disabled") is not True or pack.get("authority_level") != "L1":
            raise P117SelectorError("action_authority_enabled")


def _validate_outcome_binding(action_packs: Sequence[Mapping[str, Any]], outcomes: Sequence[Mapping[str, Any]]) -> None:
    pack_ids = {str(pack["action_pack_id"]) for pack in action_packs}
    outcome_ids = {_required_text(outcome, "action_pack_id") for outcome in outcomes}
    if pack_ids != outcome_ids:
        raise P117SelectorError("unknown_outcome_action_pack_id")


def _validate_outcomes(outcomes: Sequence[Mapping[str, Any]]) -> None:
    for outcome in outcomes:
        if int(outcome.get("denominator", 0)) <= 0:
            raise P117SelectorError("missing_outcome_denominator")
        _interval(outcome)
        if "utility_delta" not in outcome:
            raise P117SelectorError("missing_utility_delta")


def _ranked_action_pack_ids(action_packs: Sequence[Mapping[str, Any]], outcomes: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    outcome_by_id = {str(outcome["action_pack_id"]): outcome for outcome in outcomes}
    return tuple(
        str(pack["action_pack_id"])
        for pack in sorted(
            action_packs,
            key=lambda pack: (-float(outcome_by_id[str(pack["action_pack_id"])]["utility_delta"]), str(pack["action_pack_id"])),
        )
    )


def _calibration(episode: Mapping[str, Any]) -> tuple[float, float]:
    profile = _mapping(episode.get("calibration_profile_ref"))
    if "calibrated_confidence" not in profile:
        raise P117SelectorError("missing_calibrated_confidence")
    confidence = float(profile["calibrated_confidence"])
    threshold = float(profile.get("acceptance_threshold", 0.0))
    return confidence, threshold


def _required_evidence_classes(action_packs: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    classes: list[str] = []
    for pack in action_packs:
        classes.extend(_text_tuple(pack.get("required_evidence_classes", ()), "invalid_required_evidence_classes", allow_empty=True))
    return tuple(dict.fromkeys(classes))


def _interval(outcome: Mapping[str, Any]) -> tuple[float, float]:
    raw = outcome.get("utility_interval")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) != 2:
        raise P117SelectorError("invalid_utility_interval")
    lower = float(raw[0])
    upper = float(raw[1])
    if lower > upper:
        raise P117SelectorError("invalid_utility_interval")
    return (round(lower, 6), round(upper, 6))


def _has_nonzero_authority(authority_receipt: Mapping[str, Any]) -> bool:
    counters = _mapping(authority_receipt.get("authority_counters"))
    if not counters:
        return True
    return any(int(value) != 0 for value in counters.values())


def _contains_forbidden_text(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if normalized in {"command", "commands", "shell", "argv", "credential", "credentials", "target_selector"} and item != 0:
                return True
            if _contains_forbidden_text(item):
                return True
        return False
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_forbidden_text(item) for item in value)
    return isinstance(value, str) and bool(_FORBIDDEN_AUTHORITY_TEXT.search(value))


def _required_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise P117SelectorError(f"missing_{key}")
    return value


def _text_tuple(value: Any, error: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise P117SelectorError(error)
    if not value and allow_empty:
        return ()
    normalized = tuple(str(item) for item in value if isinstance(item, str) and item)
    if len(normalized) != len(value) or (not normalized and not allow_empty):
        raise P117SelectorError(error)
    return normalized


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


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
