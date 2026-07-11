"""Deterministic P115 baseline selectors with no execution surface."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p115_ontology import (
    ACTION_PACK_SCHEMA_VERSION,
    INCIDENT_CASE_SCHEMA_VERSION,
    build_action_label,
)

BASELINE_SCHEMA_VERSION = "p115.baseline_report.v1"
_SAFE_REVERSIBILITY = frozenset({"reversible", "safe_reversible", "read_only"})
_SAFE_TARGET_SCOPES = frozenset({"local_lab", "offline_fixture", "sandbox"})
_ABSTAINING_DECISIONS = frozenset({"no_action", "investigate_more", "escalate"})


class P115BaselineError(ValueError):
    """Raised when P115 baseline input is not sealed or deterministic."""


@dataclass(frozen=True)
class P115BaselineReport:
    schema_version: str
    baseline_id: str
    labels: tuple[Mapping[str, Any], ...]
    counters: Mapping[str, int]
    report_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "baseline_id": self.baseline_id,
            "labels": [dict(label) for label in self.labels],
            "counters": dict(self.counters),
            "report_hash": self.report_hash,
        }


def safe_null_baseline(incident_cases: Sequence[Mapping[str, Any]], evidence_by_case: Mapping[str, Sequence[Mapping[str, Any]]]) -> P115BaselineReport:
    """Emit only abstention labels; never proposes an action pack."""

    labels: list[dict[str, Any]] = []
    reason_counts: dict[str, int] = {}
    for incident in _sorted_incidents(incident_cases):
        case_id = _incident_case_id(incident)
        evidence = _evidence_index(evidence_by_case.get(case_id, ()))
        missing = _missing_required_evidence(incident, evidence)
        if missing:
            label = _abstention_label(incident, "investigate_more", tuple(evidence), f"missing_required_evidence:{missing[0]}")
        else:
            label = _abstention_label(incident, "no_action", tuple(evidence), "safe_null_no_action")
        _count(reason_counts, str(label["abstention_reason"]))
        labels.append(label)
    return _report("safe_null", labels, reason_counts)


def deterministic_rule_baseline(
    incident_cases: Sequence[Mapping[str, Any]],
    action_packs: Sequence[Mapping[str, Any]],
    evidence_by_case: Mapping[str, Sequence[Mapping[str, Any]]],
    prerequisite_checks_by_case: Mapping[str, Mapping[str, bool]],
    contraindication_checks_by_case: Mapping[str, Mapping[str, bool]],
) -> P115BaselineReport:
    """Select the first safe eligible frozen action pack or fail closed."""

    frozen_packs = _frozen_action_packs(action_packs)
    labels: list[dict[str, Any]] = []
    reason_counts: dict[str, int] = {}
    for incident in _sorted_incidents(incident_cases):
        case_id = _incident_case_id(incident)
        evidence = _evidence_index(evidence_by_case.get(case_id, ()))
        missing = _missing_required_evidence(incident, evidence)
        if missing:
            label = _abstention_label(incident, "investigate_more", tuple(evidence), f"missing_required_evidence:{missing[0]}")
            _count(reason_counts, str(label["abstention_reason"]))
            labels.append(label)
            continue
        if "privileged_scope_required" in evidence:
            label = _abstention_label(incident, "escalate", tuple(evidence), "human_authorized_operation")
            _count(reason_counts, str(label["abstention_reason"]))
            labels.append(label)
            continue
        if {"transient_recovery_pattern", "error_slope_negative"} <= set(evidence):
            label = _abstention_label(incident, "no_action", tuple(evidence), "measured_natural_recovery_control")
            _count(reason_counts, str(label["abstention_reason"]))
            labels.append(label)
            continue

        candidate = _select_candidate(
            incident,
            frozen_packs,
            evidence,
            prerequisite_checks_by_case.get(case_id, {}),
            contraindication_checks_by_case.get(case_id, {}),
        )
        if candidate.action_pack is None:
            label = _abstention_label(incident, candidate.decision, tuple(evidence), candidate.reason)
        else:
            pack = candidate.action_pack
            label = build_action_label(
                {
                    "case_id": case_id,
                    "decision": "act",
                    "action_pack_ids": [str(pack["action_id"])],
                    "evidence_ids": _sorted_evidence_ids_for_pack(pack, evidence),
                    "prerequisite_checks": dict(prerequisite_checks_by_case.get(case_id, {})),
                    "contraindication_checks": dict(contraindication_checks_by_case.get(case_id, {})),
                    "expected_benefit": float(_mapping(pack.get("expected_effect")).get("benefit", 1.0)),
                    "expected_harm": float(_mapping(pack.get("blast_radius")).get("expected_harm", 0.0)),
                    "validation_plan": dict(_mapping(pack.get("validation_query"))),
                    "rollback_plan": dict(_mapping(pack.get("rollback_plan"))),
                    "abstention_reason": None,
                },
                eligible_action_pack_ids=_eligible_pack_ids(incident),
            ).to_dict()
        _count(reason_counts, candidate.reason)
        labels.append(label)
    return _report("deterministic_rule", labels, reason_counts)


@dataclass(frozen=True)
class _Selection:
    decision: str
    reason: str
    action_pack: Mapping[str, Any] | None = None


def _select_candidate(
    incident: Mapping[str, Any],
    frozen_packs: Mapping[str, Mapping[str, Any]],
    evidence: Mapping[str, Mapping[str, Any]],
    prerequisite_checks: Mapping[str, bool],
    contraindication_checks: Mapping[str, bool],
) -> _Selection:
    eligible_ids = _eligible_pack_ids(incident)
    unknown = [pack_id for pack_id in eligible_ids if pack_id not in frozen_packs]
    if unknown:
        return _Selection("investigate_more", f"unknown_action_pack:{unknown[0]}")

    unsafe_reasons: list[str] = []
    for pack_id in eligible_ids:
        pack = frozen_packs[pack_id]
        reason = _pack_blocker(pack, evidence, prerequisite_checks, contraindication_checks)
        if reason is None:
            return _Selection("act", f"selected_action_pack:{pack_id}", pack)
        unsafe_reasons.append(reason)

    if not eligible_ids:
        return _Selection("no_action", "no_eligible_action_pack")
    reason = sorted(unsafe_reasons)[0]
    decision = "escalate" if _escalation_blocker(reason) else "investigate_more"
    return _Selection(decision, reason)


def _pack_blocker(
    pack: Mapping[str, Any],
    evidence: Mapping[str, Mapping[str, Any]],
    prerequisite_checks: Mapping[str, bool],
    contraindication_checks: Mapping[str, bool],
) -> str | None:
    if pack.get("authority_level") != "L1" or pack.get("executor_disabled") is not True or pack.get("executable_body") is not None:
        return "unsafe_authority"
    if str(pack.get("target_scope", "")) not in _SAFE_TARGET_SCOPES:
        return "non_local_target_scope"
    if str(pack.get("reversibility", "")) not in _SAFE_REVERSIBILITY:
        return "risky_irreversible_action"
    if _truthy(pack.get("requires_human_authorization")) or _truthy(_mapping(pack.get("blast_radius")).get("requires_human_authorization")):
        return "human_authorized_operation"
    if not _mapping(pack.get("validation_query")):
        return "missing_validation"
    if not _mapping(pack.get("rollback_plan")):
        return "missing_rollback"
    for prerequisite in _text_list(pack.get("prerequisites")):
        if prerequisite_checks.get(prerequisite) is not True:
            return f"missing_prerequisite:{prerequisite}"
    for contraindication in _text_list(pack.get("contraindications")):
        if contraindication_checks.get(contraindication) is not False:
            return f"active_or_unknown_contraindication:{contraindication}"
    missing_signals = [signal for signal in _text_list(pack.get("expected_evidence")) if signal not in evidence]
    if missing_signals:
        return f"missing_pack_evidence:{missing_signals[0]}"
    return None


def _frozen_action_packs(action_packs: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    frozen: dict[str, Mapping[str, Any]] = {}
    for pack in action_packs:
        if pack.get("schema_version") != ACTION_PACK_SCHEMA_VERSION:
            raise P115BaselineError("invalid_action_pack_schema")
        action_id = _required_text(pack, "action_id")
        if action_id in frozen:
            raise P115BaselineError(f"duplicate_action_pack:{action_id}")
        expected_hash = stable_hash({key: value for key, value in pack.items() if key != "pack_hash"})
        if pack.get("pack_hash") != expected_hash:
            raise P115BaselineError(f"unfrozen_action_pack:{action_id}")
        frozen[action_id] = dict(pack)
    return frozen


def _sorted_incidents(incident_cases: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    incidents = tuple(sorted(incident_cases, key=_incident_case_id))
    for incident in incidents:
        if incident.get("schema_version") != INCIDENT_CASE_SCHEMA_VERSION:
            raise P115BaselineError("invalid_incident_case_schema")
    return incidents


def _incident_case_id(incident: Mapping[str, Any]) -> str:
    return _required_text(incident, "case_id")


def _eligible_pack_ids(incident: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(_text_list(incident.get("eligible_action_pack_ids"))))


def _evidence_index(evidence_rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    evidence: dict[str, Mapping[str, Any]] = {}
    for row in evidence_rows:
        evidence_id = str(row.get("evidence_id") or row.get("id") or row.get("evidence_class") or row.get("class") or "")
        if not evidence_id:
            raise P115BaselineError("missing_evidence_id")
        if row.get("complete", True) is not True or row.get("present", True) is not True:
            continue
        if evidence_id in evidence:
            raise P115BaselineError(f"duplicate_evidence:{evidence_id}")
        evidence[evidence_id] = dict(row)
    return evidence


def _missing_required_evidence(incident: Mapping[str, Any], evidence: Mapping[str, Mapping[str, Any]]) -> tuple[str, ...]:
    classes = {str(row.get("evidence_class") or row.get("class") or evidence_id) for evidence_id, row in evidence.items()}
    return tuple(item for item in _text_list(incident.get("required_evidence_classes")) if item not in classes and item not in evidence)


def _sorted_evidence_ids_for_pack(pack: Mapping[str, Any], evidence: Mapping[str, Mapping[str, Any]]) -> list[str]:
    expected = set(_text_list(pack.get("expected_evidence")))
    return sorted(evidence_id for evidence_id, row in evidence.items() if evidence_id in expected or str(row.get("evidence_class") or row.get("class")) in expected)


def _abstention_label(incident: Mapping[str, Any], decision: str, evidence_ids: Sequence[str], reason: str) -> dict[str, Any]:
    if decision not in _ABSTAINING_DECISIONS:
        raise P115BaselineError("invalid_abstention_decision")
    return build_action_label(
        {
            "case_id": _incident_case_id(incident),
            "decision": decision,
            "action_pack_ids": [],
            "evidence_ids": sorted(evidence_ids) or ["no_complete_evidence"],
            "prerequisite_checks": {},
            "contraindication_checks": {},
            "expected_benefit": 0.0,
            "expected_harm": 0.0,
            "validation_plan": {"read_only": True, "baseline": "abstain"},
            "rollback_plan": {"required": False, "reason": "no_action_executed"},
            "abstention_reason": reason,
        },
        eligible_action_pack_ids=_eligible_pack_ids(incident),
    ).to_dict()


def _report(baseline_id: str, labels: Sequence[Mapping[str, Any]], reason_counts: Mapping[str, int]) -> P115BaselineReport:
    counters = {
        "case_count": len(labels),
        "act_count": sum(1 for label in labels if label["decision"] == "act"),
        "no_action_count": sum(1 for label in labels if label["decision"] == "no_action"),
        "investigate_more_count": sum(1 for label in labels if label["decision"] == "investigate_more"),
        "escalate_count": sum(1 for label in labels if label["decision"] == "escalate"),
        "action_execution_count": 0,
        "llm_call_count": 0,
        "network_call_count": 0,
        "shell_execution_count": 0,
        **{f"reason_{key}": value for key, value in sorted(reason_counts.items())},
    }
    ordered_labels = [dict(label) for label in sorted(labels, key=lambda item: str(item["case_id"]))]
    payload = {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "baseline_id": baseline_id,
        "labels": ordered_labels,
        "counters": counters,
    }
    report_hash = stable_hash(payload)
    return P115BaselineReport(BASELINE_SCHEMA_VERSION, baseline_id, tuple(ordered_labels), counters, report_hash)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str) and item)


def _required_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise P115BaselineError(f"missing_{key}")
    return value


def _truthy(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.casefold() in {"true", "yes", "required"})


def _escalation_blocker(reason: str) -> bool:
    return reason in {"human_authorized_operation", "non_local_target_scope", "risky_irreversible_action", "unsafe_authority"} or reason.startswith(
        "active_or_unknown_contraindication:"
    )


def _count(counters: dict[str, int], key: str) -> None:
    counters[key] = counters.get(key, 0) + 1


__all__ = [
    "BASELINE_SCHEMA_VERSION",
    "P115BaselineError",
    "P115BaselineReport",
    "deterministic_rule_baseline",
    "safe_null_baseline",
]
