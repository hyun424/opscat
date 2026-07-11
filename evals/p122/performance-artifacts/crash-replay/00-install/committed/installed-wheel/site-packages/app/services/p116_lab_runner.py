"""Deterministic P116 paired-arm runner over the disposable P97 loopback lab."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from app.services.causal_remediation_benchmark import (
    CausalDecision,
    CausalScenario,
    IsolatedFaultLab,
    LabActionBlocked,
    RuleBasedOpsCatSelector,
)
from app.services.p110_evaluation import stable_hash
from app.services.p116_paired_outcomes import P116_REQUIRED_ARMS

P116_LAB_RUN_SCHEMA_VERSION = "p116.lab_run.v1"
P116_LAB_BOUNDARY = {
    "synthetic_local_fault_lab": True,
    "loopback_only": True,
    "external_network_enabled": False,
    "filesystem_mutation_enabled": False,
    "subprocess_execution_enabled": False,
    "credentials_enabled": False,
    "production_mutation_enabled": False,
    "arbitrary_action_enabled": False,
    "unattended_production_operation_claimed": False,
}
_EVIDENCE_ACTION_SEQUENCES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("business_invariant_failed", ("disable_faulty_feature", "rollback_deploy")),
    ("deployment_revision_changed", ("rollback_deploy", "restart_service")),
    ("db_pool_wait_high", ("recycle_connection_pool", "shed_load")),
    ("queue_lag_growing", ("restart_consumer", "scale_consumer")),
    ("cache_error_rate_high", ("bypass_cache", "evict_bad_cache_key")),
    ("dependency_timeout_rate_high", ("enable_dependency_fallback", "shed_load")),
    ("readiness_failures", ("replace_unhealthy_instance", "shed_load")),
    ("telemetry_gap_detected", ("restore_telemetry_pipeline", "restart_service")),
    ("process_restart_count_high", ("restart_service", "rollback_deploy")),
    ("oom_kills_rising", ("increase_memory_limit", "restart_service")),
    ("cpu_throttled_seconds_high", ("scale_service", "tune_cpu_limit")),
    ("open_file_descriptors_near_limit", ("restart_service", "raise_fd_limit")),
    ("disk_free_bytes_low", ("prune_safe_temp_files", "expand_storage")),
    ("packet_loss_high", ("reroute_traffic", "shed_load")),
    ("dns_resolution_failures", ("switch_dns_resolver", "refresh_service_discovery")),
    ("tls_certificate_expiring", ("renew_certificate", "reroute_traffic")),
    ("provider_quota_remaining_low", ("reduce_request_rate", "request_quota_review")),
    ("cache_miss_fanout_spike", ("enable_request_coalescing", "disable_aggressive_retries")),
    ("request_rate_above_capacity", ("scale_service", "shed_load")),
)


class P116LabRunnerError(ValueError):
    """Raised when a paired lab run cannot prove isolation."""


@dataclass(frozen=True)
class P116LabRun:
    schema_version: str
    arm_results: tuple[Mapping[str, Any], ...]
    run_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "arm_results": [dict(item) for item in self.arm_results],
            "run_hash": self.run_hash,
            "boundary": dict(P116_LAB_BOUNDARY),
        }


class P116PairedLabRunner:
    """Run five isolated counterfactual arms; never touches a production adapter."""

    def __init__(self, *, sample_size: int = 5) -> None:
        self._sample_size = sample_size
        self._selector = RuleBasedOpsCatSelector()

    def run(self, *, cases: Sequence[CausalScenario], seeds: Sequence[int]) -> P116LabRun:
        if not cases or not seeds:
            raise P116LabRunnerError("missing_cases_or_seeds")
        arm_results: list[dict[str, Any]] = []
        with IsolatedFaultLab(sample_size=self._sample_size) as lab:
            if dict(lab.boundary) != {key: P116_LAB_BOUNDARY[key] for key in lab.boundary}:
                raise P116LabRunnerError("lab_boundary_drift")
            for scenario in cases:
                for seed_value in seeds:
                    seed = int(seed_value)
                    arm_order = list(P116_REQUIRED_ARMS)
                    random.Random(f"{scenario.case_id}:{seed}").shuffle(arm_order)
                    pair_results = [self._run_arm(lab, scenario, seed, arm, order) for order, arm in enumerate(arm_order)]
                    self._validate_pair(pair_results)
                    arm_results.extend(pair_results)
        canonical = sorted(arm_results, key=lambda item: (str(item["case_id"]), int(item["seed"]), str(item["arm"])))
        payload = {"schema_version": P116_LAB_RUN_SCHEMA_VERSION, "arm_results": canonical, "boundary": P116_LAB_BOUNDARY}
        return P116LabRun(P116_LAB_RUN_SCHEMA_VERSION, tuple(canonical), stable_hash(payload))

    def _run_arm(
        self,
        lab: IsolatedFaultLab,
        scenario: CausalScenario,
        seed: int,
        arm: str,
        arm_order: int,
    ) -> dict[str, Any]:
        fingerprint = lab.reset(scenario, seed=seed)
        reset_receipt: dict[str, Any] = {
            "case_id": scenario.case_id,
            "seed": seed,
            "arm": arm,
            "arm_order": arm_order,
            "reset_fingerprint": fingerprint,
            "verified": fingerprint == lab.initial_fingerprint,
        }
        reset_receipt["receipt_hash"] = stable_hash(reset_receipt)
        pre = asdict(lab.observe())
        selected = self._selector.select(lab.public_observation(_measurement_from_dict(pre)))
        decision, actions = self._decision_for_arm(scenario, selected, arm)
        trace: list[dict[str, Any]] = []
        attempted: list[str] = []
        for action in actions:
            try:
                trace.append(asdict(lab.apply_action(action)))
                attempted.append(action)
            except LabActionBlocked as exc:
                raise P116LabRunnerError(f"unregistered_lab_action:{action}") from exc

        if arm == "selected_action" and attempted:
            validation_probe = lab.observe()
            if not validation_probe.recovered:
                followup = _evidence_followup_action(scenario.visible_evidence, attempted)
                if followup is not None:
                    try:
                        trace.append(asdict(lab.apply_action(followup)))
                        attempted.append(followup)
                    except LabActionBlocked as exc:
                        raise P116LabRunnerError(f"unregistered_lab_action:{followup}") from exc
                    decision = CausalDecision("act", tuple(attempted), "measured validation failure triggered evidence-bound follow-up")

        if arm == "rollback_action":
            after_action = asdict(lab.observe())
            rollback_fingerprint = lab.reset(scenario, seed=seed)
            if rollback_fingerprint != fingerprint:
                raise P116LabRunnerError("rollback_reset_drift")
            trace.append({"action": "lab_reset_rollback", "applied": True, "effect": "restored initial disposable fixture"})
            post = asdict(lab.observe())
            durability = asdict(lab.observe())
        else:
            after_action = None
            post = asdict(lab.observe())
            durability = asdict(lab.observe())
            if arm == "natural_recovery":
                post = asdict(lab.observe())
                durability = asdict(lab.observe())
        return {
            "case_id": scenario.case_id,
            "family": scenario.family,
            "variant": scenario.variant,
            "split": scenario.split,
            "seed": seed,
            "arm": arm,
            "initial_fingerprint": fingerprint,
            "reset_receipt": reset_receipt,
            "decision": {"route": decision.route, "actions": list(attempted), "rationale": decision.rationale},
            "action_trace": trace,
            "pre": pre,
            "after_action_before_rollback": after_action,
            "post": post,
            "durability": durability,
        }

    @staticmethod
    def _decision_for_arm(
        scenario: CausalScenario, selected: CausalDecision, arm: str
    ) -> tuple[CausalDecision, tuple[str, ...]]:
        if arm in {"no_action", "natural_recovery"}:
            return CausalDecision("observe", (), f"{arm} control"), ()
        if arm == "wrong_action":
            actions = scenario.harmful_actions[:1]
            if not actions:
                raise P116LabRunnerError("missing_wrong_action")
            return CausalDecision("act", actions, "known harmful counterfactual"), actions
        actions = tuple(selected.actions[:2])
        if selected.route != "act":
            return CausalDecision(selected.route, (), selected.rationale), ()
        if not actions or actions == ("observe_only",):
            return CausalDecision("observe", (), "safe selected no-action"), ()
        return CausalDecision("act", actions, f"{arm} selected remediation"), actions

    @staticmethod
    def _validate_pair(results: Sequence[Mapping[str, Any]]) -> None:
        arms = {str(result.get("arm", "")) for result in results}
        if arms != set(P116_REQUIRED_ARMS):
            raise P116LabRunnerError("missing_required_arm")
        if len({str(result.get("initial_fingerprint", "")) for result in results}) != 1:
            raise P116LabRunnerError("reset_contamination")
        if len({int(result.get("seed", -1)) for result in results}) != 1:
            raise P116LabRunnerError("seed_drift")
        orders = {int(MappingProxy.get(_mapping(result.get("reset_receipt")), "arm_order", -1)) for result in results}
        if orders != set(range(len(P116_REQUIRED_ARMS))):
            raise P116LabRunnerError("arm_order_drift")


class MappingProxy:
    """Tiny typed helper avoiding truthy fallback for zero-valued fields."""

    @staticmethod
    def get(value: Mapping[str, Any], key: str, default: Any) -> Any:
        return value[key] if key in value else default


def _evidence_followup_action(evidence: Sequence[str], attempted: Sequence[str]) -> str | None:
    evidence_set = set(evidence)
    attempted_set = set(attempted)
    for marker, action_sequence in _EVIDENCE_ACTION_SEQUENCES:
        if marker not in evidence_set:
            continue
        for action in action_sequence:
            if action not in attempted_set:
                return action
    return None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _measurement_from_dict(value: Mapping[str, Any]) -> Any:
    # RuleBasedOpsCatSelector only receives the public dict, while the lab helper
    # requires a LabMeasurement instance to build it.
    from app.services.causal_remediation_benchmark import LabMeasurement

    return LabMeasurement(**value)


__all__ = ["P116LabRun", "P116LabRunnerError", "P116PairedLabRunner", "P116_LAB_BOUNDARY", "P116_LAB_RUN_SCHEMA_VERSION"]
