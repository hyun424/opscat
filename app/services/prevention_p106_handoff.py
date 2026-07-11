"""Canonical P106-to-P107 handoff validation.

P107 may consume P106 eligibility evidence, but it must recompute the P107 gate
from complete canonical evidence and must never trust copied eligibility bits.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.preventive_action_benchmark import evaluate_p107_unlock_gate

REQUIRED_CANONICAL_FIELDS = frozenset(
    {
        "shared_fail_closed_results",
        "shared_fail_closed_fixture_path",
        "shared_fail_closed_fixture_hash",
        "arm_outcomes",
        "mutation_shaped_plans",
        "harmful_taxonomy_counts",
        "authority",
        "benchmark_fresh",
        "arm_fingerprint_comparable",
        "benchmark_run_identity",
    }
)

ZERO_EXECUTED = 0


@dataclass(frozen=True)
class CanonicalP106HandoffResult:
    accepted: bool
    reasons: tuple[str, ...]
    canonical_p106_gate_recomputed: bool
    caller_supplied_p107_gate_eligible_used: bool
    recomputed_p107_gate_eligible: bool
    recomputed_gate: Mapping[str, Any]
    stale_or_forged_executed_count: int = ZERO_EXECUTED
    canonical_p106_evidence_hash: str | None = None
    selected_candidate_hash: str | None = None
    registry_hash: str | None = None
    environment: str | None = None
    accepted_candidate_ids: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        data["reasons"] = list(self.reasons)
        data["accepted_candidate_ids"] = list(self.accepted_candidate_ids)
        return data


def validate_canonical_p106_handoff(
    evidence: Mapping[str, Any],
    *,
    registry_hash: str,
    environment: str,
) -> CanonicalP106HandoffResult:
    reasons: list[str] = []
    if not isinstance(evidence, Mapping):
        return _result(False, ["P106 handoff evidence must be a mapping"], {}, registry_hash, environment)

    missing = sorted(REQUIRED_CANONICAL_FIELDS - set(evidence))
    if missing:
        reasons.append(f"missing canonical P106 evidence fields: {', '.join(missing)}")

    if evidence.get("p107_unlocked") is not False:
        reasons.append("p107_unlocked must remain false in P106 evidence")

    recomputed_gate = evaluate_p107_unlock_gate(dict(evidence))
    recomputed_eligible = bool(recomputed_gate.get("p107_gate_eligible") is True)
    if not recomputed_eligible:
        reasons.append("recomputed p107_gate_eligible is false")
    if "p107_gate_eligible" in evidence:
        reasons.append("caller supplied p107_gate_eligible is not accepted; eligibility must be recomputed")

    selected_candidates = _selected_candidates(evidence)
    if not selected_candidates:
        reasons.append("missing selected candidate in canonical arm outcomes")
    candidate_ids: list[str] = []
    for candidate in selected_candidates:
        candidate_id = str(candidate.get("candidate_id", candidate.get("capability_id", "unknown")))
        candidate_ids.append(candidate_id)
        reasons.extend(_candidate_boundary_reasons(candidate, registry_hash, environment))

    if not _mutation_plans_are_boundary_only(evidence.get("mutation_shaped_plans")):
        reasons.append("mutation shaped plans must remain simulation-only and P107-gated")
    if not _arm_outcomes_are_boundary_only(evidence.get("arm_outcomes")):
        reasons.append("arm outcomes must remain simulation-only and P107-gated")
    reasons.extend(_shared_fixture_reasons(evidence))
    reasons.extend(_p105_p106_identity_reasons(evidence))

    accepted = not reasons
    selected_hash = _sha256_json(selected_candidates[0]) if selected_candidates else None
    return CanonicalP106HandoffResult(
        accepted=accepted,
        reasons=tuple(reasons),
        canonical_p106_gate_recomputed=True,
        caller_supplied_p107_gate_eligible_used=False,
        recomputed_p107_gate_eligible=recomputed_eligible,
        recomputed_gate=recomputed_gate,
        stale_or_forged_executed_count=0,
        canonical_p106_evidence_hash=_sha256_json(dict(evidence)),
        selected_candidate_hash=selected_hash,
        registry_hash=registry_hash,
        environment=environment,
        accepted_candidate_ids=tuple(candidate_ids) if accepted else tuple(),
    )


def _result(
    accepted: bool,
    reasons: list[str],
    recomputed_gate: Mapping[str, Any],
    registry_hash: str,
    environment: str,
) -> CanonicalP106HandoffResult:
    return CanonicalP106HandoffResult(
        accepted=accepted,
        reasons=tuple(reasons),
        canonical_p106_gate_recomputed=bool(recomputed_gate),
        caller_supplied_p107_gate_eligible_used=False,
        recomputed_p107_gate_eligible=bool(recomputed_gate.get("p107_gate_eligible") is True),
        recomputed_gate=dict(recomputed_gate),
        stale_or_forged_executed_count=0,
        registry_hash=registry_hash,
        environment=environment,
    )


def _selected_candidates(evidence: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    candidates: list[Mapping[str, Any]] = []
    arm_outcomes = evidence.get("arm_outcomes")
    if not isinstance(arm_outcomes, list):
        return candidates
    for outcome in arm_outcomes:
        if not isinstance(outcome, Mapping):
            continue
        result = outcome.get("result")
        if not isinstance(result, Mapping):
            continue
        candidate = result.get("selected_candidate")
        if isinstance(candidate, Mapping):
            candidates.append(candidate)
    return candidates


def _candidate_boundary_reasons(
    candidate: Mapping[str, Any],
    registry_hash: str,
    environment: str,
) -> list[str]:
    reasons: list[str] = []
    if candidate.get("execution_enabled") is not False:
        reasons.append("selected candidate execution_enabled must be false")
    if candidate.get("simulation_only") is not True:
        reasons.append("selected candidate simulation_only must be true")
    if candidate.get("p107_required_for_execution") is not True:
        reasons.append("selected candidate p107_required_for_execution must be true")
    if candidate.get("registry_hash") != registry_hash:
        reasons.append("selected candidate registry_hash does not match current registry")
    allowlist = candidate.get("safe_environment_allowlist")
    if not isinstance(allowlist, list) or environment not in {str(item) for item in allowlist}:
        reasons.append("selected candidate safe environment allowlist does not include current environment")
    if not candidate.get("capability_id") or not candidate.get("action_type"):
        reasons.append("selected candidate must bind capability_id and action_type")
    return reasons


def _mutation_plans_are_boundary_only(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(plan, Mapping) and plan.get("execution_enabled") is False and plan.get("simulation_only") is True and plan.get("p107_required_for_execution") is True for plan in value)
    )


def _arm_outcomes_are_boundary_only(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(
            isinstance(outcome, Mapping) and outcome.get("execution_enabled") is False and outcome.get("simulation_only") is True and outcome.get("p107_required_for_execution") is True
            for outcome in value
        )
    )


def _shared_fixture_reasons(evidence: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    path_value = evidence.get("shared_fail_closed_fixture_path")
    hash_value = evidence.get("shared_fail_closed_fixture_hash")
    if not isinstance(path_value, str) or not path_value:
        return ["shared fail-closed fixture path is missing"]
    path = Path(path_value)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        reasons.append("shared fail-closed fixture path does not exist")
    elif hash_value != _file_sha256(path):
        reasons.append("shared fail-closed fixture hash is stale or forged")
    return reasons


def _p105_p106_identity_reasons(evidence: Mapping[str, Any]) -> list[str]:
    identity = evidence.get("p105_p106_prerequisite_identity")
    if not isinstance(identity, str) or not identity.startswith("p105:p106:"):
        return ["p105/p106 prerequisite identity is missing or forged"]
    benchmark_identity = evidence.get("benchmark_run_identity")
    if not isinstance(benchmark_identity, (str, Mapping)):
        return ["benchmark run identity is missing"]
    return []


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
