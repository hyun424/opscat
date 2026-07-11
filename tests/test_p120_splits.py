from __future__ import annotations

import copy

import pytest

from app.services.p120_splits import (
    P120SplitError,
    build_near_duplicate_report,
    build_split_manifest,
    consume_first_unseen_score,
    validate_near_duplicate_report,
    validate_no_holdout_tuning,
    validate_split_manifest,
)


def _freeze_inputs() -> dict[str, str]:
    return {
        "source_manifest_hash": "sha256:" + "1" * 64,
        "normalization_version": "sha256:" + "2" * 64,
        "ontology_version": "sha256:" + "3" * 64,
        "ood_threshold_hash": "sha256:" + "4" * 64,
        "calibration_method_hash": "sha256:" + "5" * 64,
        "selector_hash": "sha256:" + "6" * 64,
        "prompt_hash": "sha256:" + "7" * 64,
        "parser_rules_hash": "sha256:" + "8" * 64,
        "baseline_config_hash": "sha256:" + "9" * 64,
        "seed_hash": "sha256:" + "a" * 64,
        "evaluator_hash": "sha256:" + "b" * 64,
        "release_threshold_hash": "sha256:" + "c" * 64,
    }


def _record(case_id: str, system_id: str, split: str, text: str = "checkout latency spike") -> dict[str, object]:
    return {
        "case_id": case_id,
        "split": split,
        "system_id": system_id,
        "dataset_origin": "public",
        "source_origin": "read_only_export",
        "service_architecture_class": "queue-backed-api",
        "topology_graph_family": f"{system_id}-topology",
        "telemetry_source_combination": "metrics+logs+traces",
        "incident_scenario_family": "latency",
        "action_family": "investigate",
        "time_window": f"2026-07-01T0{case_id[-1]}:00:00Z..2026-07-01T0{case_id[-1]}:10:00Z",
        "generated_vs_observed_lineage": "observed",
        "ontology_mapping_version": "ont-v1",
        "incident_text": text,
        "telemetry_window_fingerprint": f"window-{case_id}",
        "log_template_signature": f"log-{case_id}",
        "trace_structure_fingerprint": f"trace-{case_id}",
        "topology_graph_fingerprint": f"topo-{system_id}",
        "deploy_config_marker_sequence": f"deploy-{case_id}",
        "root_cause_label": "unknown",
        "ontology_path": "incident.latency",
        "action_pack_id": f"pack-{case_id}",
        "validation_probe": f"probe-{case_id}",
        "rollback_probe": f"rollback-{case_id}",
        "outcome_window_fingerprint": f"outcome-{case_id}",
        "generated_prompt_lineage": f"prompt-{case_id}",
        "seed_lineage": f"seed-{case_id}",
    }


def test_split_manifest_freezes_system_level_exclusive_splits() -> None:
    manifest = build_split_manifest(
        [_record("case-1", "sys-dev", "development"), _record("case-2", "sys-cal", "calibration"), _record("case-3", "sys-holdout", "frozen_holdout")],
        frozen_at="2026-07-12T00:00:00Z",
        freeze_inputs=_freeze_inputs(),
    )
    validate_split_manifest(manifest)
    assert manifest["status"] == "frozen"

    consumed = consume_first_unseen_score(manifest, system_id="sys-holdout", score_receipt_hash="sha256:" + "d" * 64)
    with pytest.raises(P120SplitError, match="consumed_holdout_rescored_as_pass"):
        consume_first_unseen_score(consumed, system_id="sys-holdout", score_receipt_hash="sha256:" + "e" * 64)


def test_split_manifest_rejects_system_crossing_splits_and_holdout_tuning() -> None:
    with pytest.raises(P120SplitError, match="system_id_crosses_splits:sys-a"):
        build_split_manifest(
            [_record("case-1", "sys-a", "development"), _record("case-2", "sys-a", "frozen_holdout")],
            frozen_at="2026-07-12T00:00:00Z",
            freeze_inputs=_freeze_inputs(),
        )

    manifest = build_split_manifest(
        [_record("case-1", "sys-a", "development"), _record("case-2", "sys-b", "frozen_holdout")],
        frozen_at="2026-07-12T00:00:00Z",
        freeze_inputs=_freeze_inputs(),
    )
    with pytest.raises(P120SplitError, match="holdout_tuning:sys-b"):
        validate_no_holdout_tuning(manifest, {"prompt_tuning": ["sys-b"]})


def test_near_duplicate_report_blocks_unresolved_holdout_duplicate() -> None:
    left = _record("case-1", "sys-dev", "development", text="Checkout latency spike after deploy")
    right = _record("case-2", "sys-holdout", "frozen_holdout", text="Checkout latency spike after deployment")
    right.update(
        {
            "topology_graph_fingerprint": left["topology_graph_fingerprint"],
            "telemetry_window_fingerprint": left["telemetry_window_fingerprint"],
            "action_pack_id": left["action_pack_id"],
            "outcome_window_fingerprint": left["outcome_window_fingerprint"],
        }
    )
    report = build_near_duplicate_report([left, right], threshold=0.5)
    assert report["unresolved_pairs"]
    with pytest.raises(P120SplitError, match="unresolved_holdout_duplicate"):
        validate_near_duplicate_report(report)

    adjudicated = build_near_duplicate_report([left, right], threshold=0.5, manual_adjudications=[{"left_case_id": "case-1", "right_case_id": "case-2", "decision": "remove_holdout"}])
    validate_near_duplicate_report(adjudicated)


def test_split_manifest_tamper_detection() -> None:
    manifest = build_split_manifest([_record("case-1", "sys-a", "development")], frozen_at="2026-07-12T00:00:00Z", freeze_inputs=_freeze_inputs())
    tampered = copy.deepcopy(manifest)
    tampered["records"][0]["system_id"] = "other"
    with pytest.raises(P120SplitError, match="split_manifest_tampered"):
        validate_split_manifest(tampered)
