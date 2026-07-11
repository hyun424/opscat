"""Build and run the frozen P117 benchmark over P115/P116 artifacts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p114_hypothesis_lattice import build_p114_hypothesis_lattice
from app.services.p114_re2_loader import CANDIDATE_SCHEMA_VERSION
from app.services.p115_outcome_benchmark import _action_packs
from app.services.p115_scenario_matrix import build_p115_scenario_matrix
from app.services.p117_contract import build_p117_decision_episode
from app.services.p117_evaluator import evaluate_p117_tournament
from app.services.p117_selector import select_p117_decision

P117_EPISODE_MANIFEST_SCHEMA_VERSION = "p117.episode_manifest.v1"
_EXPECTED_LABEL = {
    "action": "act",
    "no_action": "no_action",
    "investigate_more": "investigate_more",
    "contraindicated": "abstain",
    "harmful_or_ineffective": "escalate",
}


def build_p117_frozen_benchmark(
    *,
    p116_release_evidence: Mapping[str, Any],
    frozen_seed: int = 11701,
) -> dict[str, Any]:
    """Construct opaque episodes and evaluator-only labels from frozen inputs."""

    matrix = build_p115_scenario_matrix()
    labels = {str(item["case_id"]): str(item["evaluator_label"]) for item in matrix.evaluator_labels}
    records = {str(item["case_id"]): item for item in _mapping_sequence(p116_release_evidence.get("paired_outcome_records"))}
    packs = {str(item["action_id"]): item for item in _action_packs()}
    episodes: list[dict[str, Any]] = []
    hidden_labels: list[dict[str, Any]] = []
    lattices: list[dict[str, Any]] = []
    for source in matrix.cases:
        case_id = str(source["case_id"])
        evaluator_label = labels[case_id]
        expected = _EXPECTED_LABEL[evaluator_label]
        record = records.get(case_id)
        if record is None:
            raise ValueError(f"missing_p116_record:{case_id}")
        pack_id = str(_sequence(source.get("eligible_action_pack_ids"))[0])
        pack = packs[pack_id]
        visible_ids = [f"ev-metric-{stable_hash({'case': case_id, 'slot': slot})[7:23]}" for slot in (0, 1)]
        lattice = _build_lattice(source, visible_ids)
        lattices.append(lattice)
        missing_markers = ["missing_metric_window"] if expected == "investigate_more" else []
        contraindication_ids = [visible_ids[-1]] if expected == "abstain" else []
        utility_delta = float(_mapping(_mapping(record.get("slo_deltas")).get("selected_action")).get("utility_delta", 0.0))
        lower = max(0.001, utility_delta - 0.05) if expected == "act" else -0.05
        upper = utility_delta + 0.05 if expected == "act" else 0.05
        action_ref = {
            "action_pack_id": pack_id,
            "pack_hash": str(pack["pack_hash"]),
            "signature": str(pack["signature"]),
            "signer_key_id": str(pack["signer_key_id"]),
            "signed": True,
            "required_evidence_ids": visible_ids,
            "required_evidence_classes": ["metric"],
            "contraindication_evidence_ids": contraindication_ids,
            "authority_level": "L1",
            "executor_disabled": True,
            "validation_plan": dict(_mapping(pack.get("validation_query"))),
            "rollback_plan": dict(_mapping(pack.get("rollback_plan"))),
        }
        outcome_ref = {
            "outcome_id": f"outcome-{case_id}",
            "record_hash": str(record["record_hash"]),
            "split": str(source["release_role"]),
            "action_pack_id": pack_id,
            "measurement_status": str(record.get("measurement_status")),
            "utility_delta": utility_delta,
            "utility_interval": [round(lower, 6), round(upper, 6)],
            "denominator": 1,
            "controls_comparable": record.get("measurement_status") == "comparable",
            "natural_recovery_dominates": expected == "no_action",
            "source_hash": str(record["source_hash"]),
        }
        authority_receipt = _authority_receipt(case_id)
        episode = {
            "schema_version": "p117.decision_episode.v1",
            "decision_episode_id": "p117_episode_" + stable_hash({"case_id": case_id})[7:31],
            "scenario_family": str(source["scenario_family"]),
            "p114_lattice_ref": {
                "artifact_id": str(source["diagnosis_handle"]),
                "artifact_hash": str(lattice["lattice_hash"]),
                "sealed": True,
                "replay_receipt_hash": stable_hash({"lattice_hash": lattice["lattice_hash"], "replayed": True}),
            },
            "p114_selected_hypothesis_or_abstention": str(_sequence(lattice["hypotheses"])[0]["hypothesis_id"]),
            "visible_evidence_ids": visible_ids,
            "missing_evidence_markers": missing_markers,
            "p115_case_ref": {"case_id": case_id, "artifact_hash": stable_hash(source)},
            "p115_signed_action_pack_refs": [action_ref],
            "eligible_action_pack_ids": [pack_id],
            "p116_measured_outcome_refs": [outcome_ref],
            "calibration_profile_ref": {
                "profile_id": "p117-frozen-calibration-v1",
                "artifact_hash": stable_hash({"profile": "p117-frozen-calibration-v1"}),
                "calibrated_confidence": 0.98,
                "acceptance_threshold": 0.70,
            },
            "utility_profile_ref": {
                "profile_id": "p117-measured-utility-v1",
                "artifact_hash": stable_hash({"profile": "p117-measured-utility-v1"}),
                "utility_threshold": 0.0,
            },
            "evaluation_split": str(source["release_role"]),
            "frozen_seed": frozen_seed,
            "human_authorization_required": expected == "escalate",
            "authority_boundary_receipt": authority_receipt,
        }
        build_p117_decision_episode(episode)
        episodes.append(episode)
        hidden_labels.append(
            {
                "decision_episode_id": episode["decision_episode_id"],
                "expected_label": expected,
                "measured_utility_by_label": _utility_by_label(expected, utility_delta),
            }
        )
    episodes.sort(key=lambda item: str(item["decision_episode_id"]))
    hidden_labels.sort(key=lambda item: str(item["decision_episode_id"]))
    lattices.sort(key=lambda item: str(item["case_id"]))
    manifest: dict[str, Any] = {
        "schema_version": P117_EPISODE_MANIFEST_SCHEMA_VERSION,
        "matrix_hash": matrix.matrix_hash,
        "p116_release_evidence_hash": p116_release_evidence.get("release_evidence_hash"),
        "frozen_seed": frozen_seed,
        "p114_lattices": lattices,
        "episodes": episodes,
    }
    manifest["manifest_hash"] = stable_hash(manifest)
    return {"episode_manifest": manifest, "hidden_labels": hidden_labels}


def run_p117_deterministic_tournament(
    *,
    p116_release_evidence: Mapping[str, Any],
    frozen_seed: int = 11701,
) -> dict[str, Any]:
    benchmark = build_p117_frozen_benchmark(p116_release_evidence=p116_release_evidence, frozen_seed=frozen_seed)
    episodes = list(_mapping_sequence(_mapping(benchmark["episode_manifest"]).get("episodes")))
    deterministic = [select_p117_decision(item).to_dict() for item in episodes]
    safe_null = [_safe_null_output(item) for item in episodes]
    report = evaluate_p117_tournament(
        episodes=episodes,
        hidden_labels=list(_mapping_sequence(benchmark["hidden_labels"])),
        outputs_by_selector={"deterministic": deterministic, "safe_null": safe_null},
    )
    replay = evaluate_p117_tournament(
        episodes=episodes,
        hidden_labels=list(_mapping_sequence(benchmark["hidden_labels"])),
        outputs_by_selector={
            "deterministic": [select_p117_decision(item).to_dict() for item in episodes],
            "safe_null": [_safe_null_output(item) for item in episodes],
        },
    )
    return {**benchmark, "tournament_report": report, "replay_report": replay}


def _safe_null_output(episode: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "decision_episode_id": episode["decision_episode_id"],
        "selected_label": "no_action",
        "selected_action_pack_id": None,
        "ranked_action_pack_ids": [],
        "requested_evidence_classes": [],
        "cited_evidence_ids": list(_sequence(episode.get("visible_evidence_ids"))),
        "calibrated_confidence": 0.5,
        "execution_authority": "none",
        "llm_authority": "proposal_only",
        "production_authority": False,
        "credential_scope": False,
        "p118_required_for_execution": True,
    }


def _build_lattice(source: Mapping[str, Any], visible_ids: Sequence[str]) -> dict[str, Any]:
    family = str(source["scenario_family"])
    service = str(source["service"])
    nodes = [
        {
            "node_id": evidence_id,
            "modality": "metric",
            "subject": service,
            "signal": f"{family}_{index}_signal",
            "pre_value": 1.0,
            "post_value": 2.0 + index,
            "delta": 1.0 + index,
        }
        for index, evidence_id in enumerate(visible_ids)
    ]
    packet = {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "case_id": str(source["case_id"]),
        "system": "p117-frozen-local-benchmark",
        "injection_timestamp": str(_mapping(source.get("time_window")).get("start", "")),
        "evidence_graph": {"nodes": nodes, "edges": []},
        "source_integrity": {"sealed": True, "source_hash": stable_hash(source)},
    }
    return build_p114_hypothesis_lattice(packet, max_hypotheses=6)


def _utility_by_label(expected: str, action_utility: float) -> dict[str, float]:
    values = {"act": -0.4, "investigate_more": 0.1, "no_action": 0.1, "escalate": 0.1, "abstain": 0.1}
    values[expected] = max(0.2, action_utility) if expected == "act" else 0.3
    return values


def _authority_receipt(case_id: str) -> dict[str, Any]:
    contract_counters = {
        "auth": 0,
        "credentials": 0,
        "executor": 0,
        "subprocess": 0,
        "kubernetes": 0,
        "cloud": 0,
        "database_mutation": 0,
        "production_adapter": 0,
        "network_mutation": 0,
        "online_policy_write": 0,
        "production_mutation": 0,
    }
    return {
        "execution_authority": "none",
        "llm_authority": "proposal_only",
        "production_authority": False,
        "credential_scope": False,
        "p118_required_for_execution": True,
        "counters": contract_counters,
        "authority_counters": contract_counters,
        "receipt_hash": stable_hash({"case_id": case_id, "counters": contract_counters}),
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


def _mapping_sequence(value: Any) -> tuple[Mapping[str, Any], ...]:
    return tuple(item for item in _sequence(value) if isinstance(item, Mapping))


__all__ = ["P117_EPISODE_MANIFEST_SCHEMA_VERSION", "build_p117_frozen_benchmark", "run_p117_deterministic_tournament"]
