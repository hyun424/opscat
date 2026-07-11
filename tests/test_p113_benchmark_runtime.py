from __future__ import annotations

import inspect
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p113_governance import P113_OFFICIAL_TT_SOURCE_HASH


@dataclass(frozen=True)
class _Case:
    case_id: str
    system: str
    repetition: int
    fault: str = "cpu"

    @property
    def scorer_only_truth(self) -> Mapping[str, Any]:
        return {"root_service": "svc-a", "fault_type": self.fault, "repetition": self.repetition}

    def to_candidate_packet(self) -> dict[str, Any]:
        return _packet(self.case_id, system=self.system)


def _packet(case_id: str, *, system: str = "RE1-TT") -> dict[str, Any]:
    return {
        "schema_version": "p112.re1_candidate_packet.v1",
        "case_id": case_id,
        "system": system,
        "service_catalog": ["svc-a", "svc-b"],
        "metric_catalog": ["cpu"],
        "evidence": [{"evidence_id": f"ev-{case_id}", "service": "svc-a", "metric": "cpu", "value": 1.0}],
        "diagnostic_evidence": [
            {"evidence_id": f"diag-{case_id}", "service": "svc-a", "metric": "cpu", "signed_score": 1.0}
        ],
    }


def _training_cases(system: str) -> tuple[_Case, ...]:
    faults = ("cpu", "mem", "disk", "delay", "loss")
    return tuple(
        _Case(f"{system.lower()}-{fault}-{rep}", system, rep, fault)
        for rep in (1, 2, 3, 4, 5)
        for fault in faults
    )


def _tt_dataset() -> dict[str, Any]:
    packets = [_packet(f"tt-{index:03d}") for index in range(125)]
    return {
        "schema_version": "p113.blind_candidate_dataset.v1",
        "official_source_hash": P113_OFFICIAL_TT_SOURCE_HASH,
        "case_count": 125,
        "case_ids": [str(packet["case_id"]) for packet in packets],
        "candidate_packets": packets,
        "case_ids_hash": stable_hash([str(packet["case_id"]) for packet in packets]),
        "candidate_packets_hash": stable_hash({str(packet["case_id"]): packet for packet in packets}),
        "dataset_hash": stable_hash({"packets": packets}),
    }


def test_training_runtime_uses_only_ss_ob_repetitions_1_to_3(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.p113_benchmark_runtime as runtime

    calls: list[tuple[str, str, bytes]] = []

    def fake_loader(archive_path: Path, manifest_path: Path, *, hmac_key: bytes) -> tuple[_Case, ...]:
        calls.append((archive_path.name, manifest_path.name, hmac_key))
        return _training_cases("RE1-SS" if archive_path.name == "RE1-SS.zip" else "RE1-OB")

    captured: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []

    def fake_train(
        samples: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
        *,
        training_source_hash: str,
        training_repetitions: Sequence[int],
        pair_weight: float = 1.0,
    ) -> dict[str, Any]:
        captured.extend(samples)
        return {
            "schema_version": "p112.cross_system_model.v1",
            "artifact_hash": stable_hash(
                {
                    "training_source_hash": training_source_hash,
                    "training_repetitions": list(training_repetitions),
                    "case_ids": [str(packet["case_id"]) for packet, _truth in samples],
                    "pair_weight": pair_weight,
                }
            ),
            "training_repetitions": list(training_repetitions),
            "training_case_count": len(samples),
        }

    monkeypatch.setattr(runtime, "load_pinned_re1_cases", fake_loader)
    monkeypatch.setattr(runtime, "train_cross_system_model", fake_train)
    key_path = Path("evals/real_datasets/external/p110/raw/.p110-case-id-key")
    monkeypatch.setattr(Path, "read_bytes", lambda self: b"key" if self == Path("/repo") / key_path else b"unexpected")

    ss, ob = runtime.load_p113_training_corpora(Path("/repo"))
    model = runtime.train_final_p113_model(ss, ob)

    assert calls == [
        ("RE1-SS.zip", "source-manifest-re1-ss.json", b"key"),
        ("RE1-OB.zip", "source-manifest-re1-ob.json", b"key"),
    ]
    assert model["training_repetitions"] == [1, 2, 3]
    assert model["training_case_count"] == 30
    assert {truth["repetition"] for _packet, truth in captured} == {1, 2, 3}
    assert all("rep4" not in str(packet["case_id"]).lower() for packet, _truth in captured)
    assert all(int(truth["repetition"]) not in {4, 5} for _packet, truth in captured)


def test_tt_runtime_uses_packet_only_loader_and_builds_complete_diagnosis_packets(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.p113_benchmark_runtime as runtime

    def forbidden_truth_api(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("TT truth API must not be used during freeze")

    dataset = _tt_dataset()
    monkeypatch.setattr(runtime, "load_p113_blind_candidate_dataset", lambda *args, **kwargs: dataset)
    monkeypatch.setattr(runtime, "evaluate_p113_blind_predictions", forbidden_truth_api, raising=False)
    monkeypatch.setattr(runtime, "build_p112_packet", lambda packet, model: {"case_id": packet["case_id"], "packet_hash": stable_hash({"p112": packet["case_id"], "model": model["artifact_hash"]})})
    monkeypatch.setattr(
        runtime,
        "build_p113_packet",
        lambda packet, model: {
            "schema_version": "p113.decoupled_rca_packet.v1",
            "case_id": packet["case_id"],
            "packet_hash": stable_hash({"p113": packet["case_id"], "model": model["artifact_hash"]}),
            "prompt_hash": stable_hash({"prompt": packet["case_id"]}),
            "deterministic_judgment": {"ranked_services": ["svc-a"], "fault_type": "cpu"},
        },
    )

    loaded = runtime.load_p113_tt_packet_dataset(Path("tt.zip"), Path("manifest.json"), hmac_key=b"key")
    packets = runtime.build_all_p113_diagnosis_packets(loaded["candidate_packets"], {"artifact_hash": "sha256:" + "1" * 64})

    assert loaded["candidate_packets"] == dataset["candidate_packets"]
    assert len(packets.p113_packets) == 125
    assert len(packets.p112_baseline_packets) == 125
    assert packets.case_ids == tuple(f"tt-{index:03d}" for index in range(125))
    assert packets.diagnosis_packet_hash.startswith("sha256:")
    rendered = json.dumps(packets.to_manifest(), sort_keys=True)
    assert "root_service" not in rendered
    assert "fault_type" not in rendered
    assert "scorer" not in rendered


def test_build_p113_freeze_binds_official_tt_and_stable_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.p113_benchmark_runtime as runtime

    dataset = _tt_dataset()
    model = {"schema_version": "p112.cross_system_model.v1", "artifact_hash": "sha256:" + "2" * 64}
    monkeypatch.setattr(runtime, "implementation_hash", lambda root: stable_hash({"root": str(root)}))
    monkeypatch.setattr(
        runtime,
        "build_p112_packet",
        lambda packet, model: {"case_id": packet["case_id"], "packet_hash": stable_hash({"p112": packet["case_id"], "model": model["artifact_hash"]})},
    )
    monkeypatch.setattr(
        runtime,
        "build_p113_packet",
        lambda packet, model: {
            "schema_version": "p113.decoupled_rca_packet.v1",
            "case_id": packet["case_id"],
            "packet_hash": stable_hash({"p113": packet["case_id"], "model": model["artifact_hash"]}),
            "prompt_hash": stable_hash({"prompt": packet["case_id"]}),
        },
    )
    packets = runtime.build_all_p113_diagnosis_packets(dataset["candidate_packets"], model)

    first = runtime.build_p113_freeze(
        root=Path("/repo"),
        tt_dataset=dataset,
        model_artifact=model,
        diagnosis_packets=packets,
        train_case_ids=("train-1", "train-2"),
        dev_case_ids=("dev-1",),
        frozen_at="2026-07-11T12:00:00+09:00",
    )
    second = runtime.build_p113_freeze(
        root=Path("/repo"),
        tt_dataset=dataset,
        model_artifact=model,
        diagnosis_packets=packets,
        train_case_ids=("train-1", "train-2"),
        dev_case_ids=("dev-1",),
        frozen_at="2026-07-11T12:00:00+09:00",
    )

    assert first == second
    assert first["tt_source_hash"] == P113_OFFICIAL_TT_SOURCE_HASH
    assert first["tt_case_count"] == 125
    assert first["tt_case_ids"] == [f"tt-{index:03d}" for index in range(125)]
    assert first["model_hash"] == model["artifact_hash"]
    assert first["p112_baseline_hash"] == packets.p112_baseline_prediction_hash
    assert first["diagnosis_packet_hash"] == packets.diagnosis_packet_hash
    assert first["narrative_packet_hash"] == packets.narrative_packet_hash
    assert first["system_prompt_hash"] == runtime.system_prompt_hash()
    assert first["endpoint_hash"] == runtime.endpoint_request_hash()
    assert first["decoding_hash"] == runtime.decoding_hash()
    assert first["gates_hash"] == stable_hash(runtime.ACCEPTANCE_GATES)
    assert first["freeze_hash"].startswith("sha256:")
    assert first["frozen_at"].endswith("+09:00")


def test_freeze_script_writes_only_sanitized_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.p113_benchmark_runtime as runtime
    import scripts.freeze_p113_configuration as script

    dataset = _tt_dataset()
    model = {"schema_version": "p112.cross_system_model.v1", "artifact_hash": "sha256:" + "3" * 64}
    key_path = tmp_path / "case-id-key"
    output_dir = tmp_path / "freeze"
    key_path.write_bytes(b"key")
    monkeypatch.setattr(script, "ROOT", Path("/repo"))
    monkeypatch.setattr(runtime, "load_p113_training_corpora", lambda root: (_training_cases("RE1-SS")[:15], _training_cases("RE1-OB")[:15]))
    monkeypatch.setattr(runtime, "train_final_p113_model", lambda ss, ob: model)
    monkeypatch.setattr(runtime, "load_p113_tt_packet_dataset", lambda *args, **kwargs: dataset)
    monkeypatch.setattr(
        runtime,
        "build_all_p113_diagnosis_packets",
        lambda packets, model_artifact: runtime.P113DiagnosisPacketBuild(
            case_ids=tuple(str(packet["case_id"]) for packet in packets),
            p112_baseline_packets=tuple({"case_id": packet["case_id"], "packet_hash": stable_hash({"p112": packet["case_id"]})} for packet in packets),
            p113_packets=tuple(
                {
                    "case_id": packet["case_id"],
                    "packet_hash": stable_hash({"p113": packet["case_id"]}),
                    "prompt_hash": stable_hash({"prompt": packet["case_id"]}),
                }
                for packet in packets
            ),
        ),
    )
    monkeypatch.setattr(runtime, "implementation_hash", lambda root: stable_hash({"code": str(root)}))

    assert script.main(["--output-dir", str(output_dir), "--hmac-key", str(key_path), "--frozen-at", "2026-07-11T12:00:00+09:00"]) == 0

    written = {path.name for path in output_dir.iterdir()}
    assert written == {"p113-model.json", "taint-ledger.json", "freeze-manifest.json", "packet-hash-manifest.json"}
    rendered = "\n".join(path.read_text(encoding="utf-8") for path in output_dir.iterdir())
    for forbidden in ("scorer_only", "scorer_truth", "root_service", "fault_type", "source_path"):
        assert forbidden not in rendered
    manifest = json.loads((output_dir / "packet-hash-manifest.json").read_text(encoding="utf-8"))
    assert manifest["case_count"] == 125
    assert len(manifest["p113_packet_hashes"]) == 125
    assert len(manifest["p112_baseline_packet_hashes"]) == 125


def test_runtime_and_freeze_script_do_not_import_or_use_tt_truth_api() -> None:
    import app.services.p113_benchmark_runtime as runtime
    import scripts.freeze_p113_configuration as script

    runtime_source = inspect.getsource(runtime)
    script_source = inspect.getsource(script)

    assert "evaluate_p113_blind_predictions" not in runtime_source
    assert "evaluate_p113_blind_predictions" not in script_source
    assert "to_scorer_truth" not in runtime_source
    assert "to_scorer_truth" not in script_source
    assert "load_p113_blind_candidate_dataset" in runtime_source
