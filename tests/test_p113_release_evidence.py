from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p113_benchmark_runtime import ACCEPTANCE_GATES
from app.services.p113_governance import P113_OFFICIAL_TT_SOURCE_HASH
from app.services.p113_release_evidence import (
    CRYPTO_REVIEW_SCHEMA_VERSION,
    produce_p113_release_evidence,
    render_p113_release_markdown,
)
from scripts.build_p113_release_evidence import main as build_main


def _rate(value: float, denominator: int = 125) -> dict[str, Any]:
    return {"value": value, "numerator": round(value * denominator), "denominator": denominator}


def _freeze() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "p113.fresh_blind_freeze.v1",
        "status": "frozen",
        "benchmark_role": "fresh_blind",
        "tt_source_hash": P113_OFFICIAL_TT_SOURCE_HASH,
        "tt_case_count": 125,
        "tt_case_ids_hash": stable_hash([f"tt-{index:03d}" for index in range(125)]),
        "model_hash": "sha256:" + "1" * 64,
        "p112_baseline_hash": "sha256:" + "2" * 64,
        "diagnosis_packet_hash": "sha256:" + "3" * 64,
        "narrative_packet_hash": "sha256:" + "4" * 64,
        "system_prompt_hash": "sha256:" + "5" * 64,
        "endpoint_hash": "sha256:" + "6" * 64,
        "decoding_hash": "sha256:" + "7" * 64,
        "code_hash": "sha256:" + "8" * 64,
        "gates_hash": stable_hash(ACCEPTANCE_GATES),
        "frozen_at": "2026-07-11T12:00:00+09:00",
        "narrative_subset_case_ids": [f"tt-{index:03d}" for index in range(25)],
        "action_contract_status": "disabled",
        "action_execution_enabled": False,
        "credential_access_enabled": False,
        "auth_authority": "none",
    }
    payload["freeze_hash"] = stable_hash(payload)
    return payload


def _packet_manifest(freeze: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "p113.packet_hash_manifest.v1",
        "case_count": 125,
        "case_ids_hash": freeze["tt_case_ids_hash"],
        "p112_baseline_prediction_hash": freeze["p112_baseline_hash"],
        "diagnosis_packet_hash": freeze["diagnosis_packet_hash"],
        "narrative_packet_hash": freeze["narrative_packet_hash"],
        "p112_baseline_packet_hashes": {f"tt-{index:03d}": f"sha256:{index:064x}"[-71:] for index in range(125)},
        "p113_packet_hashes": {f"tt-{index:03d}": f"sha256:{index + 200:064x}"[-71:] for index in range(125)},
    }


def _blind_eval(*, service_top1: float, fault_accuracy: float, abstention: float = 0.0, safety: dict[str, int] | None = None) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": "p113.blind_evaluation_report.v1",
        "official_source_hash": P113_OFFICIAL_TT_SOURCE_HASH,
        "summary": {"case_count": 125, "candidate_packet_hash": "sha256:" + "9" * 64},
        "metrics": {
            "service_top1": _rate(service_top1),
            "service_top3": _rate(0.92),
            "fault_accuracy": _rate(fault_accuracy),
            "evidence_precision": _rate(0.95),
            "abstention_rate": _rate(abstention),
        },
        "by_fault": {fault: {"metrics": {"fault_accuracy": _rate(0.60, 25)}} for fault in ("cpu", "mem", "disk", "delay", "loss")},
        "safety": safety
        or {
            "truth_leak_count": 0,
            "unsafe_suggestion_count": 0,
            "executed_action_count": 0,
            "provider_write_count": 0,
            "credential_count": 0,
            "shell_command_count": 0,
            "production_adapter_count": 0,
            "mutation_count": 0,
        },
        "governance": {"freeze_hash": _freeze()["freeze_hash"], "score_after_freeze": True},
    }
    report["evaluation_hash"] = stable_hash({key: value for key, value in report.items() if key != "evaluation_hash"})
    return report


def _narrative_eval(run_id: str) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": "p113.evaluation_report.v1",
        "run_id": run_id,
        "packet_set_hash": "sha256:" + "a" * 64,
        "result_set_hash": stable_hash({"run_id": run_id}),
        "summary": {"case_count": 25},
        "metrics": {
            "raw_contract_valid_rate": _rate(0.96, 25),
            "normalized_contract_valid_rate": _rate(0.96, 25),
            "narrative_valid_rate": _rate(0.96, 25),
            "diagnosis_preservation_rate": _rate(1.0, 25),
            "evidence_citation_valid_rate": _rate(1.0, 25),
            "bounded_suggestion_rate": _rate(1.0, 25),
            "replay_hash_consistency_rate": _rate(1.0, 25),
            "action_authority_disabled_rate": _rate(1.0, 25),
        },
        "safety": {
            "harmful_raw_action_count": 0,
            "unsafe_normalized_suggestion_count": 0,
            "executed_action_count": 0,
            "action_authority_enabled_count": 0,
        },
        "rows": [{"case_id": "redacted"}],
    }
    report["evaluation_hash"] = stable_hash(report)
    return report


def _repeat(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": "p113.repeat_evaluation_report.v1",
        "first_run_id": first["run_id"],
        "second_run_id": second["run_id"],
        "packet_set_hash": first["packet_set_hash"],
        "first_evaluation_hash": first["evaluation_hash"],
        "second_evaluation_hash": second["evaluation_hash"],
        "summary": {"case_count": 25},
        "metrics": {
            "diagnosis_agreement_rate": _rate(1.0, 25),
            "narrative_status_agreement_rate": _rate(1.0, 25),
        },
    }
    report["repeat_evaluation_hash"] = stable_hash(report)
    return report


def _crypto(release_binding_hash: str = "sha256:pending") -> dict[str, Any]:
    return {
        "schema_version": CRYPTO_REVIEW_SCHEMA_VERSION,
        "reviewer_id": "external-reviewer",
        "reviewer_independent": True,
        "self_attested": False,
        "signature_verified": True,
        "provider_receipts_verified": True,
        "artifact_hashes_verified": True,
        "release_binding_hash": release_binding_hash if release_binding_hash != "sha256:pending" else "sha256:" + "e" * 64,
    }


def _inputs() -> dict[str, Any]:
    freeze = _freeze()
    first = _narrative_eval("narrative-a")
    second = _narrative_eval("narrative-b")
    return {
        "acquisition_verification": {
            "verified": True,
            "sha256": P113_OFFICIAL_TT_SOURCE_HASH.removeprefix("sha256:"),
            "case_count": 125,
        },
        "freeze_manifest": freeze,
        "packet_manifest": _packet_manifest(freeze),
        "p112_baseline_evaluation": _blind_eval(service_top1=0.80, fault_accuracy=0.84),
        "diagnosis_evaluation": _blind_eval(service_top1=0.84, fault_accuracy=0.88),
        "diagnosis_contract_evaluation": _narrative_eval("diagnosis-contract"),
        "narrative_evaluations": [first, second],
        "repeat_evaluation": _repeat(first, second),
        "cryptographic_review": _crypto(),
    }


def test_release_passes_with_all_bound_evidence_and_independent_crypto() -> None:
    release = produce_p113_release_evidence(**_inputs())

    assert release["release_qualified"] is True
    assert release["stop_reason"] is None
    assert release["gates"]["cryptographic_review"] is True
    assert "rows" not in json.dumps(release)
    assert "root_service" not in json.dumps(release)


def test_release_fails_closed_when_diagnosis_fails_even_if_narrative_absent() -> None:
    inputs = _inputs()
    inputs["diagnosis_evaluation"] = _blind_eval(service_top1=0.79, fault_accuracy=0.88)
    inputs["narrative_evaluations"] = []
    inputs["repeat_evaluation"] = None

    release = produce_p113_release_evidence(**inputs)

    assert release["release_qualified"] is False
    assert release["stop_reason"] == "diagnosis_gates_failed"
    assert release["gates"]["service_top1"] is False
    assert release["gates"]["narrative_evidence_present"] is False


def test_release_fails_closed_on_missing_or_self_attested_crypto_review() -> None:
    inputs = _inputs()

    missing = produce_p113_release_evidence(**{**inputs, "cryptographic_review": None})
    self_attested = produce_p113_release_evidence(**{**inputs, "cryptographic_review": {**_crypto(), "reviewer_id": "opscat-release-builder", "self_attested": True}})

    assert missing["release_qualified"] is False
    assert missing["gates"]["cryptographic_review"] is False
    assert self_attested["release_qualified"] is False
    assert self_attested["gates"]["cryptographic_review"] is False


def test_release_rejects_forged_hashes_case_counts_and_run_dependence() -> None:
    inputs = _inputs()
    forged_freeze = {**inputs["freeze_manifest"], "diagnosis_packet_hash": "sha256:" + "f" * 64}
    forged_repeat = {**inputs["repeat_evaluation"], "second_run_id": inputs["repeat_evaluation"]["first_run_id"]}

    forged_release = produce_p113_release_evidence(**{**inputs, "freeze_manifest": forged_freeze})
    dependent_release = produce_p113_release_evidence(**{**inputs, "repeat_evaluation": forged_repeat})

    assert forged_release["release_qualified"] is False
    assert forged_release["gates"]["freeze_manifest_hash"] is False
    assert forged_release["gates"]["diagnosis_packet_hash_match"] is False
    assert dependent_release["release_qualified"] is False
    assert dependent_release["gates"]["run_independence"] is False


def test_release_enforces_zero_counters_and_narrative_rates_on_both_runs() -> None:
    inputs = _inputs()
    bad_narrative = {**_narrative_eval("narrative-bad")}
    bad_narrative["metrics"] = {**bad_narrative["metrics"], "raw_contract_valid_rate": _rate(0.88, 25)}
    bad_safety = {**inputs["diagnosis_evaluation"], "safety": {**inputs["diagnosis_evaluation"]["safety"], "credential_count": 1}}

    narrative_release = produce_p113_release_evidence(**{**inputs, "narrative_evaluations": [inputs["narrative_evaluations"][0], bad_narrative]})
    safety_release = produce_p113_release_evidence(**{**inputs, "diagnosis_evaluation": bad_safety})

    assert narrative_release["release_qualified"] is False
    assert narrative_release["gates"]["narrative_raw_contract_valid_rate"] is False
    assert safety_release["release_qualified"] is False
    assert safety_release["gates"]["zero_credentials"] is False


def test_cli_writes_machine_report_and_markdown_without_case_level_truth(tmp_path: Path) -> None:
    inputs = _inputs()
    paths = {}
    for name, value in inputs.items():
        if name == "narrative_evaluations":
            continue
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        paths[name] = path
    narrative_paths = []
    for index, value in enumerate(inputs["narrative_evaluations"]):
        path = tmp_path / f"narrative-{index}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        narrative_paths.append(path)
    out_json = tmp_path / "release.json"
    out_md = tmp_path / "release.md"

    assert (
        build_main(
            [
                "--acquisition-verification",
                str(paths["acquisition_verification"]),
                "--freeze-manifest",
                str(paths["freeze_manifest"]),
                "--packet-manifest",
                str(paths["packet_manifest"]),
                "--p112-baseline-evaluation",
                str(paths["p112_baseline_evaluation"]),
                "--diagnosis-evaluation",
                str(paths["diagnosis_evaluation"]),
                "--diagnosis-contract-evaluation",
                str(paths["diagnosis_contract_evaluation"]),
                "--narrative-evaluation",
                str(narrative_paths[0]),
                "--narrative-evaluation",
                str(narrative_paths[1]),
                "--repeat-evaluation",
                str(paths["repeat_evaluation"]),
                "--cryptographic-review",
                str(paths["cryptographic_review"]),
                "--output",
                str(out_json),
                "--markdown-output",
                str(out_md),
            ]
        )
        == 0
    )

    release = json.loads(out_json.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")
    assert release["release_qualified"] is True
    assert "release_qualified: true" in markdown
    assert "redacted" not in markdown
    assert render_p113_release_markdown(release) == markdown
