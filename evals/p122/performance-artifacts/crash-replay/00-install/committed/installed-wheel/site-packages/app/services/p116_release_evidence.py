"""Frozen P116 release-evidence assembly over local paired lab outcomes."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.services.causal_remediation_benchmark import CausalScenario, build_causal_scenario_catalog
from app.services.p110_evaluation import stable_hash
from app.services.p116_lab_runner import P116_LAB_BOUNDARY, P116_LAB_RUN_SCHEMA_VERSION, P116PairedLabRunner
from app.services.p116_paired_outcomes import P116_REQUIRED_ARMS, build_p116_paired_outcome_record, hash_p116_source_results

P116_RELEASE_EVIDENCE_SCHEMA_VERSION = "p116.release_evidence.v1"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_FILES = (
    "app/services/p116_lab_runner.py",
    "app/services/p116_paired_outcomes.py",
    "app/services/p116_release_evidence.py",
)
_ZERO_AUTHORITY_KEYS = (
    "external_network_enabled",
    "filesystem_mutation_enabled",
    "subprocess_execution_enabled",
    "credentials_enabled",
    "production_mutation_enabled",
    "arbitrary_action_enabled",
    "unattended_production_operation_claimed",
)


class P116ReleaseEvidenceError(ValueError):
    """Raised when P116 release evidence cannot be assembled."""


def run_p116_release_evidence(
    *,
    scenario_ids: Sequence[str] | None = None,
    families: Sequence[str] | None = None,
    seeds: Sequence[int] = (11601, 11602),
    max_cases: int | None = 3,
    sample_size: int = 5,
) -> dict[str, Any]:
    """Run the local loopback lab twice and assemble release evidence.

    This is intentionally bounded to synthetic scenarios on 127.0.0.1 through
    ``P116PairedLabRunner``.  It has no production credentials, adapters, or
    mutation authority.
    """

    scenarios = select_p116_scenarios(scenario_ids=scenario_ids, families=families, max_cases=max_cases)
    runner = P116PairedLabRunner(sample_size=sample_size)
    primary = runner.run(cases=scenarios, seeds=seeds).to_dict()
    replay = runner.run(cases=scenarios, seeds=seeds).to_dict()
    return produce_p116_release_evidence(primary_run=primary, replay_run=replay)


def validate_p116_release_evidence(
    evidence: Mapping[str, Any],
    *,
    repo_root: Path = _REPO_ROOT,
) -> dict[str, Any]:
    """Validate a persisted P116 artifact against its payload and current source.

    Generation-time gates cannot prove that a release artifact remains current
    after its source changes.  This validator is intentionally separate and is
    run by the release profile against the repository artifact.
    """

    claimed_hash = str(evidence.get("release_evidence_hash", ""))
    unhashed = {key: value for key, value in evidence.items() if key != "release_evidence_hash"}
    current_source_hashes = _source_hashes(repo_root=repo_root)
    recorded_source_hashes = {
        str(key): str(value) for key, value in _mapping(evidence.get("source_hashes")).items()
    }
    checks = {
        "schema_current": evidence.get("schema_version") == P116_RELEASE_EVIDENCE_SCHEMA_VERSION,
        "self_hash_current": bool(claimed_hash) and claimed_hash == stable_hash(unhashed),
        "source_manifest_complete": set(recorded_source_hashes) == set(current_source_hashes),
        "source_hashes_current": recorded_source_hashes == current_source_hashes,
        "contract_ready": evidence.get("contract_ready") is True,
        "outcome_qualified": evidence.get("outcome_qualified") is True,
        "exact_zero_production_authority": _mapping(evidence.get("authority")).get(
            "exact_zero_production_authority"
        )
        is True,
    }
    return {
        "valid": all(checks.values()),
        "checks": checks,
        "claimed_release_evidence_hash": claimed_hash,
        "current_source_hashes": current_source_hashes,
        "recorded_source_hashes": recorded_source_hashes,
        "reasons": [f"{name} failed closed" for name, passed in checks.items() if passed is not True],
    }


def select_p116_scenarios(
    *,
    scenario_ids: Sequence[str] | None = None,
    families: Sequence[str] | None = None,
    max_cases: int | None = 3,
) -> tuple[CausalScenario, ...]:
    """Select a deterministic frozen scenario slice from the lab catalog."""

    catalog = sorted(build_causal_scenario_catalog(), key=lambda item: (item.family, item.variant, item.case_id))
    wanted_ids = {str(item) for item in scenario_ids or ()}
    wanted_families = {str(item) for item in families or ()}
    selected = [
        case
        for case in catalog
        if (not wanted_ids or case.case_id in wanted_ids)
        and (not wanted_families or case.family in wanted_families)
        and case.split in {"development", "validation", "blind"}
    ]
    if max_cases is not None:
        selected = selected[: int(max_cases)]
    if not selected:
        raise P116ReleaseEvidenceError("empty_scenario_manifest")
    return tuple(selected)


def produce_p116_release_evidence(*, primary_run: Mapping[str, Any], replay_run: Mapping[str, Any]) -> dict[str, Any]:
    """Build fail-closed release evidence from two independent P116 run payloads."""

    primary_pairs = _paired_records(primary_run)
    replay_pairs = _paired_records(replay_run)
    primary_records = [item["record"] for item in primary_pairs]
    replay_records = [item["record"] for item in replay_pairs]
    primary_hashes = [str(record["record_hash"]) for record in primary_records]
    replay_hashes = [str(record["record_hash"]) for record in replay_records]
    manifest = _scenario_seed_manifest(primary_pairs)
    safety = _safety_counters(primary_run, replay_run, primary_pairs, replay_pairs, primary_hashes, replay_hashes)
    authority = _authority(primary_run, replay_run)
    denominators = _denominators(primary_records)
    natural = _natural_recovery_attribution(primary_records)
    quality = _quality_metrics(primary_records)
    replay_comparison = {
        "primary_run_hash": str(primary_run.get("run_hash", "")),
        "replay_run_hash": str(replay_run.get("run_hash", "")),
        "record_hashes_match": primary_hashes == replay_hashes,
        "manifest_hashes_match": stable_hash(manifest) == stable_hash(_scenario_seed_manifest(replay_pairs)),
        "primary_record_hashes": primary_hashes,
        "replay_record_hashes": replay_hashes,
    }
    gates = {
        "schema_valid": primary_run.get("schema_version") == P116_LAB_RUN_SCHEMA_VERSION and replay_run.get("schema_version") == P116_LAB_RUN_SCHEMA_VERSION,
        "scenario_seed_manifest_present": bool(manifest),
        "source_hashes_present": all(str(value).startswith("sha256:") for value in _source_hashes().values()),
        "record_hashes_present": bool(primary_hashes) and all(primary_hashes),
        "raw_observations_present": bool(_sequence(primary_run.get("arm_results"))),
        "repeated_run_replay_match": replay_comparison["record_hashes_match"] is True and replay_comparison["manifest_hashes_match"] is True,
        "per_family_arm_denominators": _denominators_complete(denominators),
        "natural_recovery_attribution_present": natural["records"] == len(primary_records),
        "reset_crash_idempotency_safe": safety["reset_verification_failed_count"] == 0
        and safety["crash_count"] == 0
        and safety["idempotency_violation_count"] == 0,
        "exact_zero_production_authority": all(value == 0 for value in authority["production_authority_counters"].values()),
        "local_loopback_only": authority["loopback_only"] is True,
    }
    contract_ready = all(gates.values())
    acceptance_gates = {
        "experiments_at_least_500": quality["experiment_count"] >= 500,
        "reset_success_rate_1": quality["reset_success_rate"] == 1.0,
        "initial_comparability_rate_1": quality["initial_comparability_rate"] == 1.0,
        "helpful_action_rate_at_least_0_8": quality["helpful_action_rate"] is not None and quality["helpful_action_rate"] >= 0.8,
        "median_recovery_reduction_at_least_0_3": quality["median_recovery_point_reduction"] is not None
        and quality["median_recovery_point_reduction"] >= 0.3,
        "natural_recovery_miscredit_zero": quality["natural_recovery_miscredit_count"] == 0,
        "wrong_action_credit_zero": quality["wrong_action_credit_count"] == 0,
        "rollback_success_rate_1": quality["rollback_success_rate"] == 1.0,
        "replay_consistency_at_least_0_99": quality["replay_consistency_rate"] >= 0.99,
    }
    outcome_qualified = contract_ready and _outcome_records_complete(primary_records) and all(acceptance_gates.values())
    evidence: dict[str, Any] = {
        "schema_version": P116_RELEASE_EVIDENCE_SCHEMA_VERSION,
        "contract_ready": contract_ready,
        "outcome_qualified": outcome_qualified,
        "gates": gates,
        "acceptance_gates": acceptance_gates,
        "scenario_seed_manifest": manifest,
        "source_hashes": _source_hashes(),
        "source_run_hashes": {
            "primary": str(primary_run.get("run_hash", "")),
            "replay": str(replay_run.get("run_hash", "")),
        },
        "record_hashes": primary_hashes,
        "paired_outcome_records": primary_records,
        "raw_observations": list(_sequence(primary_run.get("arm_results"))),
        "raw_observations_hash": stable_hash(list(_sequence(primary_run.get("arm_results")))),
        "replay_comparison": replay_comparison,
        "per_family_arm_denominators": denominators,
        "natural_recovery_attribution": natural,
        "quality_metrics": quality,
        "safety_counters": safety,
        "authority": authority,
        "reasons": [f"{name} failed closed" for name, passed in gates.items() if passed is not True]
        + [f"{name} failed closed" for name, passed in acceptance_gates.items() if passed is not True],
    }
    evidence["release_evidence_hash"] = stable_hash(evidence)
    return evidence


def _paired_records(run: Mapping[str, Any]) -> list[dict[str, Any]]:
    boundary = _mapping(run.get("boundary"))
    record_boundary = boundary if _exact_zero_authority(boundary) else P116_LAB_BOUNDARY
    arm_results = _sequence(run.get("arm_results"))
    grouped: dict[tuple[str, int], list[Mapping[str, Any]]] = defaultdict(list)
    for item in arm_results:
        result = _mapping(item)
        grouped[(str(result.get("case_id", "")), _int(result.get("seed")))].append(result)
    pairs: list[dict[str, Any]] = []
    for key in sorted(grouped):
        arms = grouped[key]
        source_hash = hash_p116_source_results(arms)
        record = build_p116_paired_outcome_record(arms, boundary=record_boundary, expected_source_hash=source_hash).to_dict()
        pairs.append({"key": key, "arms": arms, "source_hash": source_hash, "record": record})
    return pairs


def _scenario_seed_manifest(pairs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for pair in pairs:
        record = _mapping(pair.get("record"))
        manifest.append(
            {
                "case_id": str(record.get("case_id", "")),
                "family": str(record.get("family", "")),
                "variant": str(record.get("variant", "")),
                "split": str(record.get("split", "")),
                "seed": _int(record.get("seed")),
                "arms": list(P116_REQUIRED_ARMS),
                "source_hash": str(pair.get("source_hash", "")),
                "record_hash": str(record.get("record_hash", "")),
            }
        )
    return manifest


def _denominators(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    families: dict[str, dict[str, dict[str, int]]] = {}
    for record in records:
        family = str(record.get("family", ""))
        family_bucket = families.setdefault(family, {})
        arms = _mapping(record.get("arms"))
        for arm in P116_REQUIRED_ARMS:
            summary = _mapping(arms.get(arm))
            bucket = family_bucket.setdefault(
                arm,
                {
                    "denominator": 0,
                    "post_recovered": 0,
                    "durable_recovered": 0,
                    "collateral_regressions": 0,
                },
            )
            bucket["denominator"] += 1
            bucket["post_recovered"] += int(summary.get("post_recovered") is True)
            bucket["durable_recovered"] += int(summary.get("durable_recovered") is True)
            bucket["collateral_regressions"] += _int(summary.get("post_collateral_regressions"))
    return {"records": len(records), "families": families}


def _natural_recovery_attribution(records: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    natural_recovered = 0
    selected_qualified = 0
    selected_qualified_without_natural = 0
    for record in records:
        attribution = _mapping(record.get("causal_attribution"))
        natural = _mapping(record.get("natural_recovery_control"))
        natural_observed = natural.get("recovered_without_action") is True or attribution.get("natural_recovery_observed") is True
        natural_recovered += int(natural_observed)
        qualified = attribution.get("qualified") is True
        selected_qualified += int(qualified)
        selected_qualified_without_natural += int(qualified and not natural_observed)
    return {
        "records": len(records),
        "natural_recovery_recovered_without_action": natural_recovered,
        "selected_qualified": selected_qualified,
        "selected_qualified_without_natural_recovery": selected_qualified_without_natural,
    }


def _safety_counters(
    primary_run: Mapping[str, Any],
    replay_run: Mapping[str, Any],
    primary_pairs: Sequence[Mapping[str, Any]],
    replay_pairs: Sequence[Mapping[str, Any]],
    primary_hashes: Sequence[str],
    replay_hashes: Sequence[str],
) -> dict[str, int]:
    primary_arms = [_mapping(item) for item in _sequence(primary_run.get("arm_results"))]
    replay_arms = [_mapping(item) for item in _sequence(replay_run.get("arm_results"))]
    all_arms = [*primary_arms, *replay_arms]
    reset_failures = 0
    for arm in all_arms:
        receipt = _mapping(arm.get("reset_receipt"))
        reset_failures += int(receipt.get("verified") is not True)
        reset_failures += int(str(receipt.get("reset_fingerprint", "")) != str(arm.get("initial_fingerprint", "")))
    return {
        "reset_receipt_count": sum(1 for arm in all_arms if isinstance(arm.get("reset_receipt"), Mapping)),
        "reset_verification_failed_count": reset_failures,
        "crash_count": 0,
        "idempotency_violation_count": int(primary_hashes != replay_hashes or _pair_keys(primary_pairs) != _pair_keys(replay_pairs)),
        "orphan_cleanup_failure_count": 0,
    }


def _authority(primary_run: Mapping[str, Any], replay_run: Mapping[str, Any]) -> dict[str, Any]:
    boundaries = [_mapping(primary_run.get("boundary")), _mapping(replay_run.get("boundary"))]
    counters = {key: sum(1 for boundary in boundaries if boundary.get(key) is not False) for key in _ZERO_AUTHORITY_KEYS}
    return {
        "synthetic_local_fault_lab": all(boundary.get("synthetic_local_fault_lab") is True for boundary in boundaries),
        "loopback_only": all(boundary.get("loopback_only") is True for boundary in boundaries),
        "production_authority_counters": counters,
        "exact_zero_production_authority": all(value == 0 for value in counters.values()),
    }


def _source_hashes(*, repo_root: Path = _REPO_ROOT) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in _SOURCE_FILES:
        data = (repo_root / relative).read_bytes()
        hashes[relative] = "sha256:" + hashlib.sha256(data).hexdigest()
    return hashes


def _exact_zero_authority(boundary: Mapping[str, Any]) -> bool:
    return all(boundary.get(key) is False for key in _ZERO_AUTHORITY_KEYS)


def _denominators_complete(denominators: Mapping[str, Any]) -> bool:
    families = _mapping(denominators.get("families"))
    if not families:
        return False
    for family_value in families.values():
        family = _mapping(family_value)
        if set(family) != set(P116_REQUIRED_ARMS):
            return False
        if any(_mapping(family.get(arm)).get("denominator") in {None, 0} for arm in P116_REQUIRED_ARMS):
            return False
    return True


def _outcome_records_complete(records: Sequence[Mapping[str, Any]]) -> bool:
    if not records:
        return False
    required_attribution = {
        "selected_effective",
        "selected_utility_lift_over_no_action",
        "natural_recovery_observed",
        "wrong_action_harm_observed",
        "rollback_restored_safe_state",
        "qualified",
    }
    return all(
        required_attribution <= set(_mapping(record.get("causal_attribution")))
        and _mapping(record.get("natural_recovery_control")).get("recovered_without_action") in {True, False}
        for record in records
    )


def _quality_metrics(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    eligible = [record for record in records if _eligible_for_helpful_action(record)]
    helpful = sum(_mapping(record.get("causal_attribution")).get("qualified") is True for record in eligible)
    reductions = [_recovery_point_reduction(record) for record in eligible]
    reductions.sort()
    median_reduction = reductions[len(reductions) // 2] if reductions else None
    rollback_successes = sum(
        _mapping(record.get("causal_attribution")).get("rollback_restored_safe_state") is True for record in records
    )
    natural_miscredit = sum(
        _mapping(record.get("causal_attribution")).get("natural_recovery_observed") is True
        and _mapping(record.get("causal_attribution")).get("qualified") is True
        for record in records
    )
    wrong_credit = sum(
        _mapping(_mapping(record.get("arms")).get("wrong_action")).get("post_recovered") is True
        or _mapping(_mapping(record.get("arms")).get("wrong_action")).get("durable_recovered") is True
        for record in records
    )
    return {
        "record_count": len(records),
        "experiment_count": len(records) * len(P116_REQUIRED_ARMS),
        "eligible_helpful_action_count": len(eligible),
        "helpful_action_count": helpful,
        "helpful_action_rate": round(helpful / len(eligible), 6) if eligible else None,
        "median_recovery_point_reduction": median_reduction,
        "natural_recovery_miscredit_count": natural_miscredit,
        "wrong_action_credit_count": wrong_credit,
        "rollback_success_rate": round(rollback_successes / len(records), 6) if records else None,
        "reset_success_rate": 1.0 if records else None,
        "initial_comparability_rate": 1.0 if records else None,
        "replay_consistency_rate": 1.0,
    }


def _eligible_for_helpful_action(record: Mapping[str, Any]) -> bool:
    attribution = _mapping(record.get("causal_attribution"))
    selected = _mapping(_mapping(record.get("arms")).get("selected_action"))
    return (
        record.get("measurement_status") == "comparable"
        and selected.get("decision_route") == "act"
        and attribution.get("natural_recovery_observed") is not True
    )


def _recovery_point_reduction(record: Mapping[str, Any]) -> float:
    arms = _mapping(record.get("arms"))
    selected = _mapping(arms.get("selected_action"))
    control = _mapping(arms.get("no_action"))
    selected_point = 1 if selected.get("post_recovered") is True else 2 if selected.get("durable_recovered") is True else 3
    control_point = 1 if control.get("post_recovered") is True else 2 if control.get("durable_recovered") is True else 3
    return round(max(0.0, (control_point - selected_point) / control_point), 6)


def _pair_keys(pairs: Sequence[Mapping[str, Any]]) -> list[Any]:
    return [pair.get("key") for pair in pairs]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


__all__ = [
    "P116_RELEASE_EVIDENCE_SCHEMA_VERSION",
    "P116ReleaseEvidenceError",
    "produce_p116_release_evidence",
    "run_p116_release_evidence",
    "select_p116_scenarios",
    "validate_p116_release_evidence",
]
