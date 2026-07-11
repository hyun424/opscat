from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p113_decoupled_rca import ACTION_CONTRACT_STATUS
from app.services.p113_governance import select_p113_narrative_subset

MODEL_HASH = "sha256:" + "1" * 64
CODE_HASH = "sha256:" + "2" * 64
SYSTEM_PROMPT_HASH = "sha256:" + "3" * 64
ENDPOINT_HASH = "sha256:" + "4" * 64
DECODING_HASH = "sha256:" + "5" * 64


class _TrainCase:
    def __init__(self, case_id: str) -> None:
        self.case_id = case_id


def _candidate_packets(count: int = 125) -> list[dict[str, Any]]:
    return [
        {
            "schema_version": "p112.re1_candidate_packet.v1",
            "case_id": f"tt-{index:03d}",
            "system": "RE1-TT",
            "service_catalog": ["svc-a", "svc-b"],
            "evidence": [{"id": f"ev-tt-{index:03d}", "service": "svc-a", "metric": "cpu", "value": 1.0}],
            "diagnostic_evidence": [{"evidence_id": f"ev-tt-{index:03d}", "service": "svc-a", "metric": "cpu", "signed_score": 8.0}],
        }
        for index in range(count)
    ]


def _p112_packet(case_id: str) -> dict[str, Any]:
    return {
        "schema_version": "p112.multistage_rca_packet.v1",
        "case_id": case_id,
        "model_scores": {
            "artifact_hash": MODEL_HASH,
            "ranked_services": ["svc-a", "svc-b"],
            "ranked_faults": ["cpu", "mem"],
        },
        "evidence_ids": [f"ev-{case_id}"],
        "packet_hash": stable_hash({"p112": case_id}),
    }


def _p113_packet(case_id: str) -> dict[str, Any]:
    scores = {
        "artifact_hash": MODEL_HASH,
        "ranked_services": ["svc-a", "svc-b"],
        "ranked_faults": ["cpu", "mem"],
        "ranked_pairs": [
            {"service": "svc-a", "fault": "cpu", "score": 0.1},
            {"service": "svc-b", "fault": "mem", "score": 0.9},
        ],
    }
    judgment = {
        "schema_version": "p113.deterministic_judgment.v1",
        "source": "sealed_packet_model_scores",
        "ranked_services": ["svc-a", "svc-b"],
        "ranked_faults": ["cpu", "mem"],
        "fault_type": "cpu",
        "evidence_refs": [f"ev-{case_id}"],
        "confidence": 0.75,
        "abstain": False,
        "model_scores_hash": _sha256_json(scores),
        "packet_model_artifact_hash": MODEL_HASH,
        "action_contract_status": ACTION_CONTRACT_STATUS,
    }
    judgment["judgment_hash"] = stable_hash({key: value for key, value in judgment.items() if key != "judgment_hash"})
    packet: dict[str, Any] = {
        "schema_version": "p113.decoupled_rca_packet.v1",
        "case_id": case_id,
        "system_id": "RE1-TT",
        "service_allowlist": ["svc-a", "svc-b"],
        "fault_allowlist": ["cpu", "mem", "disk", "delay", "loss"],
        "evidence": [{"id": f"ev-{case_id}", "service": "svc-a", "metric": "cpu", "value": 1.0}],
        "evidence_ids": [f"ev-{case_id}"],
        "diagnostic_evidence": [{"evidence_id": f"ev-{case_id}", "service": "svc-a", "metric": "cpu", "signed_score": 8.0}],
        "model_scores": scores,
        "deterministic_judgment": judgment,
        "source_hashes": {"source_packet_hash": stable_hash({"source": case_id}), "model_artifact_hash": MODEL_HASH},
        "p112_packet_hash": stable_hash({"p112": case_id}),
        "prompt_hash": stable_hash({"prompt": case_id}),
    }
    packet["packet_hash"] = stable_hash({key: value for key, value in packet.items() if key != "packet_hash"})
    return packet


def _packet_build(script: Any, case_ids: Sequence[str]) -> Any:
    return script.runtime.P113DiagnosisPacketBuild(
        case_ids=tuple(case_ids),
        p112_baseline_packets=tuple(_p112_packet(case_id) for case_id in case_ids),
        p113_packets=tuple(_p113_packet(case_id) for case_id in case_ids),
    )


def _freeze(packet_build: Any, *, subset: Sequence[str] | None = None) -> dict[str, Any]:
    frozen = {
        "schema_version": "p113.fresh_blind_freeze.v1",
        "status": "frozen",
        "benchmark_role": "fresh_blind",
        "tt_source_hash": "sha256:tt",
        "tt_case_count": 125,
        "tt_case_ids": list(packet_build.case_ids),
        "model_hash": MODEL_HASH,
        "p112_baseline_hash": packet_build.p112_baseline_prediction_hash,
        "diagnosis_packet_hash": packet_build.diagnosis_packet_hash,
        "narrative_packet_hash": packet_build.narrative_packet_hash,
        "system_prompt_hash": SYSTEM_PROMPT_HASH,
        "endpoint_hash": ENDPOINT_HASH,
        "decoding_hash": DECODING_HASH,
        "code_hash": CODE_HASH,
        "gates_hash": stable_hash({"gates": "test"}),
        "frozen_at": "2026-07-11T00:00:00+00:00",
        "narrative_subset_case_ids": list(subset or packet_build.case_ids[:25]),
        "action_contract_status": "disabled",
        "action_execution_enabled": False,
        "credential_access_enabled": False,
        "auth_authority": "none",
    }
    frozen["freeze_hash"] = stable_hash({key: value for key, value in frozen.items() if key != "freeze_hash"})
    return frozen


def _write_freeze_dir(path: Path, frozen: Mapping[str, Any]) -> None:
    path.mkdir(parents=True)
    (path / "freeze-manifest.json").write_text(json.dumps(frozen), encoding="utf-8")
    (path / "p113-model.json").write_text(json.dumps({"artifact_hash": MODEL_HASH}), encoding="utf-8")
    (path / "case-id-key").write_bytes(b"p113-test-case-id-key")


def _hmac_args(freeze_dir: Path) -> list[str]:
    return ["--hmac-key", str(freeze_dir / "case-id-key")]


def _patch_common(monkeypatch: pytest.MonkeyPatch, script: Any, packet_build: Any) -> list[Sequence[Mapping[str, Any]]]:
    packets = _candidate_packets()
    captured_predictions: list[Sequence[Mapping[str, Any]]] = []
    monkeypatch.setattr(script.runtime, "load_p113_training_corpora", lambda root: ((_TrainCase("train-a"),), (_TrainCase("train-b"),)))
    monkeypatch.setattr(script.runtime, "train_final_p113_model", lambda ss, ob: {"artifact_hash": MODEL_HASH})
    monkeypatch.setattr(script.runtime, "load_p113_tt_packet_dataset", lambda *args, **kwargs: {"candidate_packets": packets})
    monkeypatch.setattr(script.runtime, "build_all_p113_diagnosis_packets", lambda candidate_packets, model: packet_build)
    monkeypatch.setattr(script.runtime, "implementation_hash", lambda root: CODE_HASH)
    monkeypatch.setattr(script.runtime, "system_prompt_hash", lambda: SYSTEM_PROMPT_HASH)
    monkeypatch.setattr(script.runtime, "endpoint_request_hash", lambda: ENDPOINT_HASH)
    monkeypatch.setattr(script.runtime, "decoding_hash", lambda: DECODING_HASH)
    monkeypatch.setattr(script.runtime, "ACCEPTANCE_GATES", {"service_top1_min": 0.8, "fault_accuracy_min": 0.8, "zero_executed_actions": True})

    def fake_evaluate(
        archive_path: Path,
        manifest_path: Path,
        predictions: Sequence[Mapping[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        captured_predictions.append(predictions)
        assert kwargs["frozen"]["freeze_hash"]
        return {
            "schema_version": "p113.blind_evaluation_report.v1",
            "summary": {"case_count": len(predictions)},
            "metrics": {
                "service_top1": {"value": 0.9},
                "fault_accuracy": {"value": 0.9},
                "evidence_precision": {"value": 1.0},
                "abstention_rate": {"value": 0.0},
            },
            "safety": {"executed_action_count": 0, "harmful_action_count": 0, "truth_leak_count": 0},
            "evaluation_hash": stable_hash({"count": len(predictions), "index": len(captured_predictions)}),
        }

    monkeypatch.setattr(script, "evaluate_p113_blind_predictions", fake_evaluate)
    return captured_predictions


def test_diagnosis_mode_rebuilds_validates_scores_and_uses_no_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import scripts.run_p113_blind_benchmark as script

    packet_build = _packet_build(script, [f"tt-{index:03d}" for index in range(125)])
    freeze_dir = tmp_path / "freeze"
    output_dir = tmp_path / "out"
    captured_predictions = _patch_common(monkeypatch, script, packet_build)
    _write_freeze_dir(freeze_dir, _freeze(packet_build))
    monkeypatch.setenv("NVIDIA_API_KEY", "super-secret")
    monkeypatch.setattr(script, "NvidiaP110CandidateProvider", lambda *args, **kwargs: pytest.fail("diagnosis must not construct provider"))

    assert script.main(
        [
            "diagnosis",
            "--freeze-dir",
            str(freeze_dir),
            "--output-dir",
            str(output_dir),
            "--scoring-started-at",
            "2026-07-11T00:00:01+00:00",
            *_hmac_args(freeze_dir),
        ]
    ) == 0

    assert len(captured_predictions) == 2
    assert len(captured_predictions[0]) == 125
    assert len(captured_predictions[1]) == 125
    gate = json.loads((output_dir / "diagnosis-gate-report.json").read_text(encoding="utf-8"))
    assert gate["passed"] is True
    assert (output_dir / "p112-baseline-evaluation.json").exists()
    assert (output_dir / "p113-diagnosis-evaluation.json").exists()
    contract_eval = json.loads((output_dir / "p113-diagnosis-contract-evaluation.json").read_text(encoding="utf-8"))
    assert contract_eval["metrics"]["diagnosis_preservation_rate"]["value"] == 1.0
    assert contract_eval["metrics"]["replay_hash_consistency_rate"]["value"] == 1.0
    assert (output_dir / "diagnosis-comparison.json").exists()
    assert "super-secret" not in capsys.readouterr().out


def test_narrative_requires_passed_diagnosis_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.run_p113_blind_benchmark as script

    packet_build = _packet_build(script, [f"tt-{index:03d}" for index in range(125)])
    freeze_dir = tmp_path / "freeze"
    gate_path = tmp_path / "missing-gate.json"
    _write_freeze_dir(freeze_dir, _freeze(packet_build))
    _patch_common(monkeypatch, script, packet_build)

    with pytest.raises(SystemExit) as exc:
        script.main(
            [
                "narrative",
                "--freeze-dir",
                str(freeze_dir),
                "--diagnosis-gate-report",
                str(gate_path),
                "--output-dir",
                str(tmp_path / "out"),
                *_hmac_args(freeze_dir),
            ]
        )

    assert exc.value.code == 2


def test_narrative_mode_uses_exact_frozen_subset_and_batches_with_explicit_nvidia_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.run_p113_blind_benchmark as script

    case_ids = [f"tt-{index:03d}" for index in range(125)]
    subset = list(select_p113_narrative_subset([{"case_id": case_id} for case_id in case_ids]))
    packet_build = _packet_build(script, case_ids)
    freeze_dir = tmp_path / "freeze"
    output_dir = tmp_path / "out"
    gate_path = tmp_path / "diagnosis-gate-report.json"
    _patch_common(monkeypatch, script, packet_build)
    _write_freeze_dir(freeze_dir, _freeze(packet_build, subset=subset))
    gate_path.write_text(json.dumps({"passed": True, "freeze_hash": json.loads((freeze_dir / "freeze-manifest.json").read_text(encoding="utf-8"))["freeze_hash"]}), encoding="utf-8")
    provider_init: list[dict[str, Any]] = []
    calls: list[str] = []

    class FakeProvider:
        name = "nvidia"
        model_calls_enabled = True

        def __init__(self, **kwargs: Any) -> None:
            provider_init.append(kwargs)

        def diagnose(self, packet: Mapping[str, Any], prompt: str) -> str:
            calls.append(str(packet["case_id"]))
            return json.dumps(
                {
                    "explanation": "The sealed diagnosis is consistent.",
                    "contradictions": [],
                    "inspection_suggestions": [f"inspect svc-a cpu metrics using ev-{packet['case_id']}"],
                }
            )

    monkeypatch.setattr(script, "NvidiaP110CandidateProvider", FakeProvider)

    assert script.main(
        [
            "narrative",
            "--freeze-dir",
            str(freeze_dir),
            "--diagnosis-gate-report",
            str(gate_path),
            "--output-dir",
            str(output_dir),
            "--case-offset",
            "5",
            "--max-cases",
            "4",
            *_hmac_args(freeze_dir),
        ]
    ) == 0

    assert calls == subset[5:9]
    assert provider_init == [{"model": script.runtime.MODEL, "system_prompt": script.P113_SYSTEM_PROMPT}]
    payload = json.loads((output_dir / "narrative-results-offset-5-count-4.json").read_text(encoding="utf-8"))
    assert [item["case_id"] for item in payload["results"]] == subset[5:9]
    assert all("raw_response" in item for item in payload["results"])
    evaluation = json.loads((output_dir / "narrative-evaluation-offset-5-count-4.json").read_text(encoding="utf-8"))
    assert evaluation["safety"]["executed_action_count"] == 0
    assert evaluation["safety"]["action_authority_enabled_count"] == 0


def test_narrative_rejects_duplicate_or_drifted_frozen_subset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.run_p113_blind_benchmark as script

    packet_build = _packet_build(script, [f"tt-{index:03d}" for index in range(125)])
    frozen = _freeze(packet_build, subset=["tt-000", "tt-000", *[f"tt-{index:03d}" for index in range(1, 24)]])
    freeze_dir = tmp_path / "freeze"
    gate_path = tmp_path / "diagnosis-gate-report.json"
    _write_freeze_dir(freeze_dir, frozen)
    gate_path.write_text(json.dumps({"passed": True, "freeze_hash": frozen["freeze_hash"]}), encoding="utf-8")
    _patch_common(monkeypatch, script, packet_build)

    with pytest.raises(SystemExit) as exc:
        script.main(
            [
                "narrative",
                "--freeze-dir",
                str(freeze_dir),
                "--diagnosis-gate-report",
                str(gate_path),
                "--output-dir",
                str(tmp_path / "out"),
                *_hmac_args(freeze_dir),
            ]
        )

    assert exc.value.code == 2


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
