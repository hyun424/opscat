from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.services.p110_candidate_runner import P110RunnerConfig, compute_p110_cache_key
from app.services.p110_evaluation import stable_hash
from scripts.merge_p110_labeled_batches import _merge_candidate_reports

OFFICIAL_SOURCE = "sha256:4a709297e0a829f0f2ee8a7792a6d74da32d663c600565b7fffc860963b840c4"


def _fixture() -> tuple[dict[str, dict[str, object]], list[dict[str, object]], P110RunnerConfig]:
    config = P110RunnerConfig(
        model="nvidia/test",
        decoding_config={"temperature": 1.0, "top_p": 0.95, "max_tokens": 16384, "reasoning_budget": 16384, "enable_thinking": True},
    )
    packets: dict[str, dict[str, object]] = {}
    truth: list[dict[str, object]] = []
    services = ("adservice", "cartservice", "checkoutservice", "currencyservice", "productcatalogservice")
    faults = ("cpu", "delay", "disk", "loss", "mem")
    for index in range(25):
        case_id = f"case-{index:02d}"
        service = services[index // 5]
        fault = faults[index % 5]
        evidence_id = f"ev-{index:02d}"
        packets[case_id] = {
            "schema_version": "p110.candidate_packet.v1",
            "case_id": case_id,
            "system_id": "online_boutique",
            "time_range": {"injection_timestamp": "1"},
            "topology": {},
            "service_allowlist": [service],
            "fault_allowlist": list(faults),
            "evidence": [{"id": evidence_id, "service": service, "metric": fault}],
            "evidence_ids": [evidence_id],
        }
        truth.append(
            {
                "schema_version": "p110.rcaeval_scorer_truth.v1",
                "case_id": case_id,
                "scorer_only_truth": {"root_service": service, "fault_type": fault, "repetition": 5},
                "official_source_hash": OFFICIAL_SOURCE,
                "evidence_ids": [evidence_id],
                "source_path": f"{service}_{fault}/5",
                "raw_hashes": {"data.csv": "a" * 64, "inject_time": "b" * 64},
            }
        )
    return packets, truth, config


def _write_batches(root: Path, packets: dict[str, dict[str, object]], truth: list[dict[str, object]], config: P110RunnerConfig) -> None:
    truth_by_id = {str(item["case_id"]): item for item in truth}
    ids = sorted(packets)
    for offset in range(0, 25, 5):
        batch_ids = ids[offset : offset + 5]
        predictions = []
        for case_id in batch_ids:
            packet = packets[case_id]
            truth_case = truth_by_id[case_id]
            scorer_truth = truth_case["scorer_only_truth"]
            evidence_ids = packet["evidence_ids"]
            assert isinstance(scorer_truth, dict)
            assert isinstance(evidence_ids, list)
            service = str(scorer_truth["root_service"])
            fault = str(scorer_truth["fault_type"])
            evidence_id = str(evidence_ids[0])
            cache_key = compute_p110_cache_key(
                model=config.model,
                packet=packet,
                prompt_schema_version=config.prompt_schema_version,
                decoding_config=config.decoding_config,
            )
            raw = {
                "case_id": case_id,
                "ranked_services": [service],
                "fault_type": fault,
                "evidence_refs": [evidence_id],
                "confidence": 0.8,
                "abstain": False,
                "advisory_actions": ["inspect evidence"],
            }
            raw_text = json.dumps(raw, sort_keys=True, separators=(",", ":"))
            predictions.append(
                {
                    "case_id": case_id,
                    "ranked_services": [service],
                    "fault_type": fault,
                    "evidence_refs": [evidence_id],
                    "confidence": 0.8,
                    "abstain": False,
                    "advisory_actions": ["inspect evidence"],
                    "validation_status": "valid",
                    "validation_errors": [],
                    "candidate_context": packet,
                    "cache_key": cache_key,
                    "model": config.model,
                    "prompt_schema_version": config.prompt_schema_version,
                    "decoding_config": dict(config.decoding_config),
                    "raw_response_sha256": hashlib.sha256(raw_text.encode()).hexdigest(),
                    "raw_response": raw_text,
                    "executed_actions": [],
                }
            )
        report = {
            "schema_version": "p110.candidate_runner_report.v1",
            "mode": "nvidia",
            "provider": "nvidia",
            "model": config.model,
            "summary": {
                "case_count": 5,
                "valid_count": 5,
                "fail_closed_count": 0,
                "network_calls_enabled": True,
                "action_execution_enabled": False,
            },
            "budget": {"provider_call_count": 5},
            "safety": {"truth_leak_count": 0, "harmful_action_count": 0, "executed_action_count": 0},
            "provenance": {
                "model": config.model,
                "prompt_schema_version": config.prompt_schema_version,
                "decoding_config": dict(config.decoding_config),
            },
            "benchmark_provenance": {
                "official_source": OFFICIAL_SOURCE,
                "repetition": 5,
                "case_offset": offset,
                "selected_case_count": 5,
                "selected_case_ids": batch_ids,
                "candidate_packets_hash": stable_hash({case_id: packets[case_id] for case_id in batch_ids}),
                "scorer_truth_hash": stable_hash({case_id: truth_by_id[case_id] for case_id in batch_ids}),
                "model": config.model,
                "prompt_schema_version": config.prompt_schema_version,
                "decoding_config": dict(config.decoding_config),
            },
            "predictions": predictions,
        }
        batch = root / f"batch-{offset // 5}"
        batch.mkdir(parents=True)
        (batch / "candidate-nvidia.json").write_text(json.dumps(report), encoding="utf-8")


def test_merge_accepts_exact_sealed_batch_provenance(tmp_path: Path) -> None:
    packets, truth, config = _fixture()
    _write_batches(tmp_path, packets, truth, config)

    predictions, report = _merge_candidate_reports(
        tmp_path,
        expected_packets=packets,
        expected_truth=truth,
        official_source=OFFICIAL_SOURCE,
    )

    assert len(predictions) == 25
    assert report["provenance"]["scorer_truth_hash"] == stable_hash(truth)
    assert report["summary"]["valid_count"] == 25


@pytest.mark.parametrize("tamper", ("source", "cache", "model", "raw_response"))
def test_merge_rejects_forged_batch_provenance(tmp_path: Path, tamper: str) -> None:
    packets, truth, config = _fixture()
    _write_batches(tmp_path, packets, truth, config)
    path = tmp_path / "batch-0/candidate-nvidia.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    if tamper == "source":
        report["benchmark_provenance"]["official_source"] = "sha256:" + "0" * 64
    elif tamper == "cache":
        report["predictions"][0]["cache_key"] = "0" * 64
    elif tamper == "raw_response":
        report["predictions"][0]["raw_response"] = '{"forged":true}'
    else:
        report["model"] = "nvidia/other"
    path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(SystemExit):
        _merge_candidate_reports(tmp_path, expected_packets=packets, expected_truth=truth, official_source=OFFICIAL_SOURCE)
