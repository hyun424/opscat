"""P116 paired measured-outcome records over existing causal benchmark results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from app.services.p110_evaluation import stable_hash

P116_PAIRED_OUTCOME_SCHEMA_VERSION = "p116.paired_outcome_record.v1"
P116_REQUIRED_ARMS = ("selected_action", "no_action", "wrong_action", "rollback_action", "natural_recovery")

_ZERO_PRODUCTION_AUTHORITY = {
    "external_network_enabled": False,
    "filesystem_mutation_enabled": False,
    "subprocess_execution_enabled": False,
    "credentials_enabled": False,
    "production_mutation_enabled": False,
    "arbitrary_action_enabled": False,
    "unattended_production_operation_claimed": False,
}


class P116PairedOutcomeError(ValueError):
    """Raised when paired measured outcomes cannot be safely compared."""


@dataclass(frozen=True)
class P116PairedOutcomeRecord:
    """Immutable P116 paired outcome record."""

    schema_version: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", _freeze(self.payload))

    def to_dict(self) -> dict[str, Any]:
        thawed = _thaw(self.payload)
        if not isinstance(thawed, dict):
            raise P116PairedOutcomeError("invalid_record_payload")
        return thawed


def hash_p116_source_results(arm_results: Sequence[Mapping[str, Any]]) -> str:
    """Hash measured source arm results in a stable arm-ordered form."""

    return stable_hash(_canonical_source_results(arm_results))


def build_p116_paired_outcome_record(
    arm_results: Sequence[Mapping[str, Any]],
    *,
    boundary: Mapping[str, Any],
    expected_source_hash: str,
) -> P116PairedOutcomeRecord:
    """Build one immutable paired record from precomputed measured arm results.

    The function intentionally consumes existing benchmark result dictionaries
    rather than running a lab or executing actions.  It fails closed unless the
    caller proves that all five arms came from the same scenario, seed, and
    initial state, with zero production authority and verifiable measurements.
    """

    _validate_no_production_authority(boundary)
    arms = _index_arms(arm_results)
    selected = arms["selected_action"]
    control = arms["no_action"]
    wrong = arms["wrong_action"]
    rollback = arms["rollback_action"]
    natural_recovery = arms["natural_recovery"]
    ordered_arms = (selected, control, wrong, rollback, natural_recovery)
    _validate_same_pairing_identity(ordered_arms)
    measurements_verifiable = all(_validate_measurements(arm) for arm in ordered_arms)
    if not expected_source_hash or expected_source_hash != hash_p116_source_results(arm_results):
        raise P116PairedOutcomeError("source_hash_drift")

    case_id = str(selected["case_id"])
    seed = int(selected["seed"])
    initial_fingerprint = str(selected["initial_fingerprint"])
    source_hash = hash_p116_source_results(arm_results)
    arm_hashes = {arm_name: stable_hash(_canonical_arm_result(arms[arm_name])) for arm_name in P116_REQUIRED_ARMS}
    payload: dict[str, Any] = {
        "schema_version": P116_PAIRED_OUTCOME_SCHEMA_VERSION,
        "case_id": case_id,
        "family": str(selected.get("family", "")),
        "variant": str(selected.get("variant", "")),
        "split": str(selected.get("split", "")),
        "seed": seed,
        "initial_state_fingerprint": initial_fingerprint,
        "recovery_window": {"measurement_points": ["post", "durability"], "durability_required": True},
        "natural_recovery_control": _natural_recovery_control(natural_recovery),
        "measurement_status": "comparable" if measurements_verifiable else "inconclusive",
        "reset_verification": {
            "same_scenario": True,
            "same_seed": True,
            "same_initial_state": True,
            "required_arms_present": True,
            "receipt_hashes": {arm_name: str(_mapping(arms[arm_name]["reset_receipt"])["receipt_hash"]) for arm_name in P116_REQUIRED_ARMS},
        },
        "arms": {arm_name: _arm_summary(arms[arm_name]) for arm_name in P116_REQUIRED_ARMS},
        "slo_deltas": {
            "selected_action": _slo_delta(selected, control),
            "wrong_action": _slo_delta(wrong, control),
        },
        "collateral_harm": {
            "selected_action": _collateral_harm(selected, control),
            "wrong_action": _collateral_harm(wrong, control),
        },
        "causal_attribution": _causal_attribution(selected, control, wrong, rollback, natural_recovery),
        "source_hash": source_hash,
        "arm_hashes": arm_hashes,
        "authority": dict(_ZERO_PRODUCTION_AUTHORITY),
    }
    payload["record_hash"] = stable_hash(payload)
    return P116PairedOutcomeRecord(schema_version=P116_PAIRED_OUTCOME_SCHEMA_VERSION, payload=payload)


def _index_arms(arm_results: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for result in arm_results:
        arm = str(result.get("arm", ""))
        if arm in indexed:
            raise P116PairedOutcomeError(f"duplicate_arm:{arm}")
        indexed[arm] = result
    missing = [arm for arm in P116_REQUIRED_ARMS if arm not in indexed]
    if missing:
        raise P116PairedOutcomeError(f"missing_arm:{','.join(missing)}")
    return {arm: indexed[arm] for arm in P116_REQUIRED_ARMS}


def _validate_same_pairing_identity(arms: Sequence[Mapping[str, Any]]) -> None:
    case_ids = {str(arm.get("case_id", "")) for arm in arms}
    if len(case_ids) != 1 or "" in case_ids:
        raise P116PairedOutcomeError("cross_scenario_comparison")
    scenario_keys = ("family", "variant", "split")
    for key in scenario_keys:
        values = {str(arm.get(key, "")) for arm in arms}
        if len(values) != 1:
            raise P116PairedOutcomeError("cross_scenario_comparison")
    seeds = {_required_int(arm, "seed") for arm in arms}
    if len(seeds) != 1:
        raise P116PairedOutcomeError("cross_seed_comparison")
    fingerprints = {str(arm.get("initial_fingerprint", "")) for arm in arms}
    if len(fingerprints) != 1 or "" in fingerprints:
        raise P116PairedOutcomeError("reset_verification_failed")
    arm_orders: set[int] = set()
    for arm in arms:
        receipt = _mapping(arm.get("reset_receipt"))
        if receipt.get("verified") is not True:
            raise P116PairedOutcomeError("reset_verification_failed")
        if str(receipt.get("reset_fingerprint", "")) != str(arm.get("initial_fingerprint", "")):
            raise P116PairedOutcomeError("reset_verification_failed")
        receipt_payload = {key: value for key, value in receipt.items() if key != "receipt_hash"}
        if str(receipt.get("receipt_hash", "")) != stable_hash(receipt_payload):
            raise P116PairedOutcomeError("reset_receipt_hash_mismatch")
        order = _required_int(receipt, "arm_order")
        if order in arm_orders:
            raise P116PairedOutcomeError("duplicate_arm_order")
        arm_orders.add(order)


def _validate_measurements(arm: Mapping[str, Any]) -> bool:
    verifiable = True
    for field in ("pre", "post", "durability"):
        measurement = _mapping(arm.get(field))
        if not measurement:
            raise P116PairedOutcomeError("missing_measurement")
        if field in {"post", "durability"} and measurement.get("verifiable") is not True:
            verifiable = False
        for key in ("availability", "latency_ms", "backlog", "correctness", "utility", "collateral_regressions", "recovered"):
            if key not in measurement:
                raise P116PairedOutcomeError("missing_measurement")
    return verifiable


def _validate_no_production_authority(boundary: Mapping[str, Any]) -> None:
    for key, expected in _ZERO_PRODUCTION_AUTHORITY.items():
        if boundary.get(key) is not expected:
            raise P116PairedOutcomeError("production_authority_enabled")


def _natural_recovery_control(control: Mapping[str, Any]) -> dict[str, Any]:
    post = _mapping(control["post"])
    durability = _mapping(control["durability"])
    return {
        "arm": "natural_recovery",
        "recovered_without_action": bool(post.get("recovered")) and bool(durability.get("recovered")),
        "post_recovered": bool(post.get("recovered")),
        "durable_recovered": bool(durability.get("recovered")),
        "utility": _number(post, "utility"),
    }


def _causal_attribution(
    selected: Mapping[str, Any],
    control: Mapping[str, Any],
    wrong: Mapping[str, Any],
    rollback: Mapping[str, Any],
    natural_recovery: Mapping[str, Any],
) -> dict[str, Any]:
    selected_post = _mapping(selected["post"])
    selected_durable = _mapping(selected["durability"])
    control_post = _mapping(control["post"])
    natural_durable = _mapping(natural_recovery["durability"])
    wrong_post = _mapping(wrong["post"])
    rollback_post = _mapping(rollback["post"])
    lift = _delta(selected_post, control_post, "utility")
    natural_recovery_observed = bool(natural_durable.get("recovered"))
    selected_effective = (
        selected_post.get("verifiable") is True
        and selected_durable.get("verifiable") is True
        and bool(selected_post.get("recovered"))
        and bool(selected_durable.get("recovered"))
        and lift >= 0.05
        and not natural_recovery_observed
        and _required_int(selected_post, "collateral_regressions") == 0
    )
    return {
        "selected_effective": selected_effective,
        "selected_utility_lift_over_no_action": lift,
        "natural_recovery_observed": natural_recovery_observed,
        "wrong_action_harm_observed": _required_int(wrong_post, "collateral_regressions") > _required_int(control_post, "collateral_regressions"),
        "rollback_restored_safe_state": _required_int(rollback_post, "collateral_regressions") == 0,
        "qualified": selected_effective and _required_int(rollback_post, "collateral_regressions") == 0,
    }


def _arm_summary(arm: Mapping[str, Any]) -> dict[str, Any]:
    post = _mapping(arm["post"])
    durability = _mapping(arm["durability"])
    decision = _mapping(arm.get("decision"))
    return {
        "arm": str(arm["arm"]),
        "decision_route": str(decision.get("route", "")),
        "actions": [str(item) for item in _sequence(decision.get("actions"))],
        "post_recovered": bool(post.get("recovered")),
        "durable_recovered": bool(durability.get("recovered")),
        "post_utility": _number(post, "utility"),
        "durable_utility": _number(durability, "utility"),
        "post_collateral_regressions": _required_int(post, "collateral_regressions"),
        "durable_collateral_regressions": _required_int(durability, "collateral_regressions"),
    }


def _slo_delta(arm: Mapping[str, Any], control: Mapping[str, Any]) -> dict[str, Any]:
    post = _mapping(arm["post"])
    control_post = _mapping(control["post"])
    durability = _mapping(arm["durability"])
    control_durability = _mapping(control["durability"])
    return {
        "availability_delta": _delta(post, control_post, "availability"),
        "latency_ms_delta": _delta(post, control_post, "latency_ms"),
        "backlog_delta": _delta(post, control_post, "backlog"),
        "correctness_delta": _delta(post, control_post, "correctness"),
        "utility_delta": _delta(post, control_post, "utility"),
        "durable_utility_delta": _delta(durability, control_durability, "utility"),
        "recovery_delta": int(bool(post.get("recovered"))) - int(bool(control_post.get("recovered"))),
        "collateral_regression_delta": _required_int(post, "collateral_regressions") - _required_int(control_post, "collateral_regressions"),
    }


def _collateral_harm(arm: Mapping[str, Any], control: Mapping[str, Any]) -> dict[str, Any]:
    post = _mapping(arm["post"])
    durability = _mapping(arm["durability"])
    control_post = _mapping(control["post"])
    control_durability = _mapping(control["durability"])
    observed = max(_required_int(post, "collateral_regressions"), _required_int(durability, "collateral_regressions"))
    baseline = max(_required_int(control_post, "collateral_regressions"), _required_int(control_durability, "collateral_regressions"))
    return {
        "observed_collateral_regressions": observed,
        "control_collateral_regressions": baseline,
        "excess_collateral_regressions": observed - baseline,
        "harmful": observed > baseline,
    }


def _canonical_source_results(arm_results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted((_canonical_arm_result(result) for result in arm_results), key=lambda item: str(item.get("arm", "")))


def _canonical_arm_result(result: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _thaw(value) for key, value in sorted(result.items(), key=lambda item: str(item[0])) if str(key) not in {"p116_arm_hash"}}


def _delta(left: Mapping[str, Any], right: Mapping[str, Any], key: str) -> float:
    return round(_number(left, key) - _number(right, key), 6)


def _number(value: Mapping[str, Any], key: str) -> float:
    raw = value.get(key)
    if not isinstance(raw, int | float) or isinstance(raw, bool):
        raise P116PairedOutcomeError("missing_measurement")
    return float(raw)


def _required_int(value: Mapping[str, Any], key: str) -> int:
    raw = value.get(key)
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise P116PairedOutcomeError("missing_measurement")
    return raw


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


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
    if isinstance(value, list):
        return [_thaw(item) for item in value]
    return value


__all__ = [
    "P116PairedOutcomeError",
    "P116PairedOutcomeRecord",
    "P116_PAIRED_OUTCOME_SCHEMA_VERSION",
    "P116_REQUIRED_ARMS",
    "build_p116_paired_outcome_record",
    "hash_p116_source_results",
]
