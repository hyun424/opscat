from __future__ import annotations

import copy
import hashlib
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

P150_LIMITATIONS = [
    "accelerated_fault_gate_plus_two_hour_local_soak",
    "no_external_provider_model_or_production_effect",
    "no_live_infrastructure",
]


def _phase() -> Any:
    return importlib.import_module("app.services.p150_unattended_soak")


def _stable_hash(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _valid_p149_release_evidence() -> dict[str, Any]:
    contracts = importlib.import_module("app.services.p147_p152_contracts")
    evidence: dict[str, Any] = {
        "schema_version": "p149.release_evidence.v1",
        "phase": "p149",
        "status": "p149_canary_outcome_control_qualified",
        "claim": "one-target canaries are SLO guarded and automatically rolled back",
        "limitations": [
            "automatic_rollback_no_production_authority",
            "one_process_owned_lab_target_only",
            "synthetic_slo_observations",
        ],
        "report_hash": "sha256:" + "1" * 64,
        "freeze_hash": "sha256:" + "2" * 64,
        "review_hash": "sha256:" + "3" * 64,
        "predecessors": [
            {
                "phase": "p148",
                "path": "evals/p148/output/release-evidence.json",
                "schema_version": "p148.release_evidence.v1",
                "required_status": "p148_reversible_lab_action_qualified",
                "file_hash": "sha256:" + "4" * 64,
                "evidence_hash": "sha256:" + "5" * 64,
            }
        ],
        "source_hashes": {path: "sha256:" + "6" * 64 for path in sorted(contracts.phase_source_paths("p149"))},
        "metrics": {
            "canary_count": 8,
            "committed_count": 1,
            "rolled_back_count": 5,
            "harmful_count": 2,
            "max_affected_targets": 1,
            "rollback_success_rate": 1.0,
            "canonical_input_verified": True,
        },
        "counters": {
            "read_attempt_count": 0,
            "read_success_count": 0,
            "model_call_count": 0,
            "external_model_call_count": 0,
            "investigation_tool_call_count": 0,
            "action_intent_count": 8,
            "action_commit_count": 1,
            "action_execution_count": 6,
            "rollback_count": 5,
            "heartbeat_count": 0,
            "deadman_count": 0,
            "artifact_write_count": 8,
            "credential_read_count": 0,
            "external_network_count": 0,
            "external_message_count": 0,
            "shell_count": 0,
            "staging_mutation_count": 0,
            "production_mutation_count": 0,
            "authority_escape_count": 0,
        },
        "passed": 8,
        "failed": 0,
        "evidence_hash": "",
    }
    evidence["evidence_hash"] = _stable_hash({key: value for key, value in evidence.items() if key != "evidence_hash"})
    return evidence


def _write_p149_release_evidence(tmp_path: Path, evidence: dict[str, Any] | None = None) -> Path:
    predecessor_path = tmp_path / "evals/p149/output/release-evidence.json"
    predecessor_path.parent.mkdir(parents=True, exist_ok=True)
    predecessor_path.write_text(
        json.dumps(evidence or _valid_p149_release_evidence(), separators=(",", ":"), ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return predecessor_path


class _FakeMonotonicClock:
    def __init__(self) -> None:
        self.now_ns = 1_000_000_000_000

    def monotonic_ns(self) -> int:
        return self.now_ns

    def sleep(self, seconds: float) -> None:
        self.now_ns += int(seconds * 1_000_000_000)


def _valid_wall_clock_artifacts(tmp_path: Path) -> tuple[dict[str, Any], Path, Path, Path]:
    phase = _phase()
    clock = _FakeMonotonicClock()
    output_dir = tmp_path / "wall-clock"
    original_rss_bytes = phase._rss_bytes
    phase._rss_bytes = lambda: 10_000_000
    try:
        phase.run_wall_clock_runner(
            output_dir=output_dir,
            resume=False,
            clock_ns=clock.monotonic_ns,
            sleeper=clock.sleep,
        )
    finally:
        phase._rss_bytes = original_rss_bytes
    result_path = output_dir / "wall-clock-result.json"
    receipt = json.loads(result_path.read_text(encoding="utf-8"))
    return receipt, result_path, output_dir / "wall-clock-cycles.jsonl", output_dir / "wall-clock-checkpoint.json"


def _fast_schedule() -> dict[str, Any]:
    return {
        "simulated_seconds": 604800,
        "scenarios": [
            "healthy",
            "incident",
            "evidence_gap",
            "injection",
            "provider_failure",
            "model_failure",
            "crash",
            "restart",
            "lease_conflict",
            "storage_pressure",
            "harmful_canary",
            "rollback",
            "kill_switch",
        ],
        "fault_classes": [
            "incident",
            "evidence_gap",
            "injection",
            "provider_failure",
            "model_failure",
            "crash",
            "restart",
            "lease_conflict",
            "storage_pressure",
            "harmful_canary",
            "rollback",
            "kill_switch",
        ],
        "limits": {
            "max_queue_depth": 256,
            "artifact_bytes": 16_777_216,
            "retries_per_tick": 2,
            "work_units_per_tick": 64,
        },
    }


def _p150_final_review(report: dict[str, Any], freeze_manifest: dict[str, Any], findings: dict[str, int] | None = None) -> dict[str, Any]:
    review = {
        "schema_version": "p150.final_review.v1",
        "phase": "p150",
        "writer_agent_id": "019f72f0-0000-7000-8000-000000000151",
        "reviewer_identity": "independent-p150-reviewer",
        "reviewer_agent_id": "019f72f0-0000-7000-8000-000000000150",
        "reviewed_at": "2026-07-16T00:00:00Z",
        "decision": "approve",
        "findings": findings or {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
        "limitations": P150_LIMITATIONS,
        "reviewed_report_hash": report["report_hash"],
        "reviewed_manifest_hash": freeze_manifest["manifest_hash"],
        "review_hash": "",
    }
    review["review_hash"] = _stable_hash({key: value for key, value in review.items() if key != "review_hash"})
    return review


def test_contract_and_predecessor_fail_closed(tmp_path: Path) -> None:
    phase = _phase()
    predecessor = _valid_p149_release_evidence()
    predecessor_path = _write_p149_release_evidence(tmp_path, predecessor)
    wall_clock, result_path, ledger_path, checkpoint_path = _valid_wall_clock_artifacts(tmp_path)
    result = phase.run_p150_qualification(
        predecessor_path=predecessor_path,
        fast_schedule=_fast_schedule(),
        wall_clock_result=wall_clock,
        wall_clock_result_path=result_path,
        wall_clock_ledger_path=ledger_path,
        wall_clock_checkpoint_path=checkpoint_path,
        output_dir=tmp_path,
        evidence_mode="isolated_test",
    )
    report = phase.validate_p150_report(result["report"])

    assert report["status"] == "p150_unattended_chaos_soak_qualified"
    assert report["predecessors"] == [
        {
            "phase": "p149",
            "path": "evals/p149/output/release-evidence.json",
            "schema_version": "p149.release_evidence.v1",
            "required_status": "p149_canary_outcome_control_qualified",
            "file_hash": phase.file_hash(predecessor_path),
            "evidence_hash": predecessor["evidence_hash"],
        }
    ]

    with pytest.raises(Exception, match="predecessor|path|required"):
        phase.run_p150_qualification(
            predecessor=predecessor,
            fast_schedule=_fast_schedule(),
            wall_clock_result=wall_clock,
            wall_clock_result_path=result_path,
            wall_clock_ledger_path=ledger_path,
            wall_clock_checkpoint_path=checkpoint_path,
            output_dir=tmp_path / "pathless-predecessor",
        )

    with pytest.raises(Exception, match="evidence.mode|invalid"):
        phase.run_p150_qualification(
            predecessor_path=predecessor_path,
            fast_schedule=_fast_schedule(),
            wall_clock_result=wall_clock,
            wall_clock_result_path=result_path,
            wall_clock_ledger_path=ledger_path,
            wall_clock_checkpoint_path=checkpoint_path,
            output_dir=tmp_path / "invalid-mode",
            evidence_mode="hash_only",
        )

    noncanonical_path = tmp_path / "release-evidence.json"
    noncanonical_path.write_text(predecessor_path.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(Exception, match="predecessor|canonical|path"):
        phase.run_p150_qualification(
            predecessor_path=noncanonical_path,
            fast_schedule=_fast_schedule(),
            wall_clock_result=wall_clock,
            wall_clock_result_path=result_path,
            wall_clock_ledger_path=ledger_path,
            wall_clock_checkpoint_path=checkpoint_path,
            output_dir=tmp_path / "noncanonical-predecessor",
        )

    forged = copy.deepcopy(predecessor)
    forged["status"] = "p149_preliminary_not_release"
    forged["evidence_hash"] = _stable_hash({key: value for key, value in forged.items() if key != "evidence_hash"})
    forged_path = _write_p149_release_evidence(tmp_path / "forged-predecessor-root", forged)
    with pytest.raises(Exception, match="p149|predecessor|status|release"):
        phase.run_p150_qualification(
            predecessor_path=forged_path,
            fast_schedule=_fast_schedule(),
            wall_clock_result=wall_clock,
            wall_clock_result_path=result_path,
            wall_clock_ledger_path=ledger_path,
            wall_clock_checkpoint_path=checkpoint_path,
            output_dir=tmp_path / "forged",
            evidence_mode="isolated_test",
        )


def test_happy_path_report_and_counters(tmp_path: Path) -> None:
    phase = _phase()
    wall_clock, result_path, ledger_path, checkpoint_path = _valid_wall_clock_artifacts(tmp_path)
    predecessor_path = _write_p149_release_evidence(tmp_path)
    result = phase.run_p150_qualification(
        predecessor_path=predecessor_path,
        fast_schedule=_fast_schedule(),
        wall_clock_result=wall_clock,
        wall_clock_result_path=result_path,
        wall_clock_ledger_path=ledger_path,
        wall_clock_checkpoint_path=checkpoint_path,
        output_dir=tmp_path,
        evidence_mode="isolated_test",
    )
    report = phase.validate_p150_report(result["report"])

    assert report["schema_version"] == "p150.report.v1"
    assert report["status"] == "p150_unattended_chaos_soak_qualified"
    assert report["metrics"]["simulated_seconds"] == 604800
    assert report["metrics"]["tick_count"] > 0
    assert report["metrics"]["wall_clock_seconds"] >= 7200
    assert report["metrics"]["wall_clock_cycles"] == 7200
    assert report["metrics"]["wall_clock_qualified"] is True
    assert report["metrics"]["unresolved_effect_count"] == 0
    assert report["predecessors"][0]["file_hash"] == phase.file_hash(predecessor_path)
    assert report["profile_hash"] == _stable_hash(
        {
            "schema_version": "p150.release_profile.v1",
            "phase": "p150",
            "case_ids": [
                f"P150-{index:03d}-{scenario}"
                for index, scenario in enumerate(_fast_schedule()["scenarios"], start=1)
            ],
            "limits": {
                **phase.FAST_LIMITS,
                "simulated_seconds": 604800,
                "wall_clock_cycles": 7200,
                "wall_clock_seconds": 7200,
                "fast_schedule_hash": _stable_hash(_fast_schedule()),
                "wall_clock_receipt_hash": wall_clock["receipt_hash"],
                "wall_clock_result_file_hash": phase.file_hash(result_path),
                "wall_clock_ledger_file_hash": phase.file_hash(ledger_path),
                "wall_clock_checkpoint_file_hash": phase.file_hash(checkpoint_path),
                "wall_clock_checkpoint_hash": wall_clock["checkpoint_hash"],
                "wall_clock_runner_instance_id": wall_clock["runner_instance_id"],
                "wall_clock_runner_mode": phase.RUNNER_MODE_INJECTED,
                "wall_clock_start_receipt_hash": wall_clock["start_receipt_hash"],
                "wall_clock_ledger_entry_count": wall_clock["ledger"]["entry_count"],
                "wall_clock_ledger_last_hash": wall_clock["ledger"]["last_entry_hash"],
                "wall_clock_resource_maxima_hash": _stable_hash(wall_clock["resource_maxima"]),
            },
        }
    )
    assert report["counters"]["credential_read_count"] == 0
    assert report["counters"]["external_network_count"] == 0
    assert report["counters"]["staging_mutation_count"] == 0
    assert report["counters"]["production_mutation_count"] == 0

    invalid_report = copy.deepcopy(report)
    invalid_report["metrics"] = dict(invalid_report["metrics"], wall_clock_cycles=7199)
    invalid_report["report_hash"] = _stable_hash({key: value for key, value in invalid_report.items() if key != "report_hash"})
    with pytest.raises(Exception, match="metrics|success|exact"):
        phase.validate_p150_report(invalid_report)

    unresolved_wall_clock = copy.deepcopy(wall_clock)
    unresolved_wall_clock["unresolved_effect_count"] = 1
    unresolved_wall_clock["receipt_hash"] = _stable_hash(
        {key: value for key, value in unresolved_wall_clock.items() if key != "receipt_hash"}
    )
    unresolved_result_path = tmp_path / "unresolved-wall-clock-result.json"
    unresolved_result_path.write_text(
        json.dumps(unresolved_wall_clock, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="unresolved.effects|qualification"):
        phase.run_p150_qualification(
            predecessor_path=predecessor_path,
            fast_schedule=_fast_schedule(),
            wall_clock_result=unresolved_wall_clock,
            wall_clock_result_path=unresolved_result_path,
            wall_clock_ledger_path=ledger_path,
            wall_clock_checkpoint_path=checkpoint_path,
            output_dir=tmp_path / "unresolved",
            evidence_mode="isolated_test",
        )


def test_fault_matrix_and_recovery(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    phase = _phase()

    def forbidden_sleep(seconds: float) -> None:
        raise AssertionError(f"accelerated soak attempted real sleep: {seconds}")

    monkeypatch.setattr(phase, "sleep", forbidden_sleep, raising=False)
    fast_result = phase.run_accelerated_soak(schedule=_fast_schedule(), output_dir=tmp_path)
    assert fast_result["simulated_seconds"] == 604800
    assert set(fast_result["fault_classes"]) == set(_fast_schedule()["fault_classes"])
    assert fast_result["scenario_count"] == 13
    assert len(fast_result["fault_classes"]) == 12
    assert fast_result["semantic_replay_match"] is True
    assert fast_result["unresolved_effect_count"] == 0
    assert fast_result["max_queue_depth"] <= 256
    assert fast_result["artifact_bytes"] <= 16_777_216
    assert fast_result["wall_clock_qualified"] is False

    replay = phase.run_accelerated_soak(schedule=_fast_schedule(), output_dir=tmp_path / "replay")
    assert replay["semantic_hash"] == fast_result["semantic_hash"]

    bad_faults = copy.deepcopy(_fast_schedule())
    bad_faults["fault_classes"] = bad_faults["fault_classes"][:-1]
    with pytest.raises(Exception, match="fault|12"):
        phase.run_accelerated_soak(schedule=bad_faults, output_dir=tmp_path / "bad-faults")

    bad_scenarios = copy.deepcopy(_fast_schedule())
    bad_scenarios["scenarios"] = bad_scenarios["scenarios"][:-1]
    with pytest.raises(Exception, match="healthy|scenarios"):
        phase.run_accelerated_soak(schedule=bad_scenarios, output_dir=tmp_path / "bad-scenarios")

    bad_limits = copy.deepcopy(_fast_schedule())
    bad_limits["limits"] = dict(bad_limits["limits"], max_queue_depth=999)
    with pytest.raises(Exception, match="limits|resource"):
        phase.run_accelerated_soak(schedule=bad_limits, output_dir=tmp_path / "bad-limits")

    monkeypatch.setattr(phase, "WALL_CLOCK_CYCLES", 3)

    class JitterClock(_FakeMonotonicClock):
        def sleep(self, seconds: float) -> None:
            self.now_ns += int(seconds * 1_000_000_000) + 750_000_000

    jitter_clock = JitterClock()
    wall_clock = phase.generate_injected_wall_clock_artifacts(
        output_dir=tmp_path / "jitter-wall-clock",
        resume=False,
        clock_ns=jitter_clock.monotonic_ns,
        sleeper=jitter_clock.sleep,
    )
    ledger_lines = (tmp_path / "jitter-wall-clock/wall-clock-cycles.jsonl").read_text(encoding="utf-8").splitlines()
    monotonic_samples = [json.loads(line)["monotonic_ns"] for line in ledger_lines]
    assert all(
        sample - previous >= phase.WALL_CLOCK_CADENCE_NS
        for previous, sample in zip([wall_clock["started_monotonic_ns"], *monotonic_samples], monotonic_samples, strict=False)
    )


def test_forgery_and_authority_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    phase = _phase()
    wall_clock, result_path, ledger_path, checkpoint_path = _valid_wall_clock_artifacts(tmp_path)

    in_memory = copy.deepcopy(wall_clock)
    in_memory["cycle_receipts"] = []
    in_memory["receipt_hash"] = _stable_hash({key: value for key, value in in_memory.items() if key != "receipt_hash"})
    with pytest.raises(Exception, match="memory|cycle|receipt|rejected"):
        phase.validate_wall_clock_result(in_memory)

    with pytest.raises(Exception, match="injected|clock|rejected"):
        phase.validate_wall_clock_result(wall_clock)

    invalid_runner_mode = copy.deepcopy(wall_clock)
    invalid_runner_mode["runner_mode"] = "forged-clock"
    with pytest.raises(Exception, match="runner.mode|clock"):
        phase.validate_wall_clock_result(invalid_runner_mode, allow_injected_test_clock=True)

    partial = copy.deepcopy(wall_clock)
    partial["elapsed_seconds"] = 7199
    partial["wall_clock_qualified"] = True
    partial["receipt_hash"] = _stable_hash({key: value for key, value in partial.items() if key != "receipt_hash"})
    with pytest.raises(Exception, match="injected|clock|rejected"):
        phase.validate_wall_clock_result(partial)

    injected = copy.deepcopy(wall_clock)
    injected["clock_source"] = "injected_fake_clock"
    injected["receipt_hash"] = _stable_hash({key: value for key, value in injected.items() if key != "receipt_hash"})
    with pytest.raises(Exception, match="injected|clock|wall"):
        phase.validate_wall_clock_result(injected)

    truncated_ledger = tmp_path / "truncated.jsonl"
    truncated_ledger.write_bytes(b"\n".join(ledger_path.read_bytes().splitlines()[:-1]) + b"\n")
    with pytest.raises(Exception, match="ledger|count|order|7200"):
        phase.validate_wall_clock_result(
            wall_clock,
            result_path=result_path,
            ledger_path=truncated_ledger,
            checkpoint_path=checkpoint_path,
            allow_injected_test_clock=True,
        )

    tampered_ledger = tmp_path / "tampered.jsonl"
    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[42])
    row["monotonic_ns"] -= 1
    row["receipt_hash"] = _stable_hash({key: value for key, value in row.items() if key != "receipt_hash"})
    lines[42] = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    tampered_ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(Exception, match="hash.chain|cadence|monotonic|ledger"):
        phase.validate_wall_clock_result(
            wall_clock,
            result_path=result_path,
            ledger_path=tampered_ledger,
            checkpoint_path=checkpoint_path,
            allow_injected_test_clock=True,
        )

    short_clock = _FakeMonotonicClock()
    with pytest.raises(Exception, match="qualified|7200|partial|cycle"):
        phase.generate_injected_wall_clock_artifacts(
            output_dir=tmp_path / "short-wall-clock",
            resume=False,
            clock_ns=short_clock.monotonic_ns,
            sleeper=short_clock.sleep,
            test_only_cycle_count=3,
        )

    forced = copy.deepcopy(wall_clock)
    forced["ended_monotonic_ns"] = forced["started_monotonic_ns"] + 7201 * 1_000_000_000
    forced["elapsed_ns"] = 7201 * 1_000_000_000
    forced["elapsed_seconds"] = 7201
    forced["receipt_hash"] = _stable_hash({key: value for key, value in forced.items() if key != "receipt_hash"})
    forced_path = tmp_path / "forced-result.json"
    forced_path.write_text(json.dumps(forced, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n", encoding="utf-8")
    with pytest.raises(Exception, match="forced|result|bytes|mismatch|elapsed|ledger"):
        phase.validate_wall_clock_result(
            forced,
            result_path=forced_path,
            ledger_path=ledger_path,
            checkpoint_path=checkpoint_path,
            allow_injected_test_clock=True,
        )

    tampered_result = copy.deepcopy(wall_clock)
    tampered_result["resource_maxima"] = dict(tampered_result["resource_maxima"], artifact_bytes=1)
    tampered_result["receipt_hash"] = _stable_hash({key: value for key, value in tampered_result.items() if key != "receipt_hash"})
    tampered_result_path = tmp_path / "tampered-result.json"
    tampered_result_path.write_text(
        json.dumps(tampered_result, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="resource|maxima|underreported"):
        phase.validate_wall_clock_result(
            tampered_result,
            result_path=tampered_result_path,
            ledger_path=ledger_path,
            checkpoint_path=checkpoint_path,
            allow_injected_test_clock=True,
        )

    bad_artifact_bytes = copy.deepcopy(wall_clock)
    bad_lines = ledger_path.read_text(encoding="utf-8").splitlines()
    bad_row = json.loads(bad_lines[0])
    bad_row["artifact_bytes"] += 1
    bad_row["receipt_hash"] = _stable_hash({key: value for key, value in bad_row.items() if key != "receipt_hash"})
    bad_lines[0] = json.dumps(bad_row, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    bad_artifact_ledger = tmp_path / "bad-artifact-bytes.jsonl"
    bad_artifact_ledger.write_text("\n".join(bad_lines) + "\n", encoding="utf-8")
    with pytest.raises(Exception, match="artifact.bytes|hash.chain|ledger"):
        phase.validate_wall_clock_result(
            bad_artifact_bytes,
            result_path=result_path,
            ledger_path=bad_artifact_ledger,
            checkpoint_path=checkpoint_path,
            allow_injected_test_clock=True,
        )

    first_row = json.loads(ledger_path.read_text(encoding="utf-8").splitlines()[0])
    assert first_row["artifact_bytes"] == len(
        json.dumps(first_row, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8") + b"\n"
    )
    monkeypatch.setattr(phase.resource, "getrusage", lambda _target: SimpleNamespace(ru_maxrss=123))
    monkeypatch.setattr(phase.sys, "platform", "linux")
    assert phase._rss_bytes() == 123 * 1024

    accelerated_forgery = phase.run_accelerated_soak(schedule=_fast_schedule(), output_dir=tmp_path)
    forged_release = dict(accelerated_forgery, wall_clock_qualified=True, wall_clock_cycles=7200, wall_clock_seconds=7200)
    with pytest.raises(Exception, match="accelerated|wall.clock|qualified"):
        phase.validate_wall_clock_result(forged_release)


def test_release_evidence_requires_zero_finding_review(tmp_path: Path) -> None:
    phase = _phase()
    wall_clock, result_path, ledger_path, checkpoint_path = _valid_wall_clock_artifacts(tmp_path)
    result = phase.run_p150_qualification(
        predecessor_path=_write_p149_release_evidence(tmp_path),
        fast_schedule=_fast_schedule(),
        wall_clock_result=wall_clock,
        wall_clock_result_path=result_path,
        wall_clock_ledger_path=ledger_path,
        wall_clock_checkpoint_path=checkpoint_path,
        output_dir=tmp_path,
        evidence_mode="isolated_test",
    )

    assert "report" in result
    assert "freeze_manifest" in result
    assert "final_review" not in result
    assert "release_evidence" not in result

    report = phase.validate_p150_report(result["report"])
    manifest = phase.validate_p150_freeze_manifest(result["freeze_manifest"])
    nonzero_review = _p150_final_review(report, manifest, findings={"p0": 0, "p1": 1, "p2": 0, "p3": 0})
    assert nonzero_review["review_hash"] == _stable_hash({key: value for key, value in nonzero_review.items() if key != "review_hash"})
    with pytest.raises(Exception, match="review|finding|p1|zero"):
        phase.validate_p150_final_review(nonzero_review, report=report, freeze_manifest=manifest)

    review = phase.validate_p150_final_review(_p150_final_review(report, manifest), report=report, freeze_manifest=manifest)
    wall_clock_evidence = phase.build_p150_wall_clock_evidence(
        wall_clock,
        result_path=result_path,
        ledger_path=ledger_path,
        checkpoint_path=checkpoint_path,
        allow_injected_test_clock=True,
    )
    with pytest.raises(Exception, match="real|runner|binding|evidence|clock"):
        phase.assemble_p150_release_evidence(
            report=report,
            freeze_manifest=manifest,
            final_review=review,
            wall_clock_evidence=wall_clock_evidence,
        )
    with pytest.raises(Exception, match="wall.clock|evidence|required|keyset"):
        phase.assemble_p150_release_evidence(
            report=report,
            freeze_manifest=manifest,
            final_review=review,
            wall_clock_evidence={},
        )
    assembled = phase.assemble_release_evidence(
        contract=phase.P150_CONTRACT,
        report=report,
        freeze_manifest=manifest,
        final_review=review,
    )
    assembled["wall_clock_evidence"] = wall_clock_evidence
    assembled["evidence_hash"] = _stable_hash({key: value for key, value in assembled.items() if key != "evidence_hash"})
    with pytest.raises(Exception, match="raw|path"):
        phase.validate_p150_release_evidence(assembled)

    hash_only_fake = copy.deepcopy(assembled)
    hash_only_fake["wall_clock_evidence"]["result_file_hash"] = "sha256:" + "9" * 64
    hash_only_fake["metrics"]["wall_clock_evidence_hash"] = _stable_hash(hash_only_fake["wall_clock_evidence"])
    hash_only_fake["evidence_hash"] = _stable_hash(
        {key: value for key, value in hash_only_fake.items() if key != "evidence_hash"}
    )
    with pytest.raises(Exception, match="raw|artifact|mismatch|real|runner"):
        phase.validate_p150_release_evidence(
            hash_only_fake,
            wall_clock_result_path=result_path,
            wall_clock_ledger_path=ledger_path,
            wall_clock_checkpoint_path=checkpoint_path,
        )

    with pytest.raises(Exception, match="real|runner|binding|evidence|clock"):
        phase.validate_p150_release_evidence(
            assembled,
            wall_clock_result_path=result_path,
            wall_clock_ledger_path=ledger_path,
            wall_clock_checkpoint_path=checkpoint_path,
        )
    with pytest.raises(Exception, match="real|runner|binding|evidence|clock"):
        phase.assemble_p150_release_evidence_from_paths(
            report=report,
            freeze_manifest=manifest,
            final_review=review,
            wall_clock_result_path=result_path,
            wall_clock_ledger_path=ledger_path,
            wall_clock_checkpoint_path=checkpoint_path,
        )

    assert manifest["schema_version"] == "p150.freeze_manifest.v1"
    assert manifest["manifest_hash"] == _stable_hash({key: value for key, value in manifest.items() if key != "manifest_hash"})
    assert review["findings"] == {"p0": 0, "p1": 0, "p2": 0, "p3": 0}
    assert review["limitations"] == P150_LIMITATIONS
    assert review["reviewed_report_hash"] == report["report_hash"]
    assert review["reviewed_manifest_hash"] == manifest["manifest_hash"]
    assert review["review_hash"] == _stable_hash({key: value for key, value in review.items() if key != "review_hash"})
    assert assembled["status"] == "p150_unattended_chaos_soak_qualified"
    assert assembled["limitations"] == P150_LIMITATIONS
    assert assembled["report_hash"] == report["report_hash"]
    assert assembled["freeze_hash"] == manifest["manifest_hash"]
    assert assembled["review_hash"] == review["review_hash"]
    assert assembled["metrics"]["wall_clock_qualified"] is True
    assert assembled["metrics"]["wall_clock_seconds"] == 7200
    assert assembled["wall_clock_evidence"] == wall_clock_evidence
    assert assembled["evidence_hash"] == _stable_hash({key: value for key, value in assembled.items() if key != "evidence_hash"})
    _assert_release_validation_requires_complete_raw_paths_or_project_root(tmp_path / "raw-path-contract")


def _assert_release_validation_requires_complete_raw_paths_or_project_root(tmp_path: Path) -> None:
    phase = _phase()
    wall_clock, result_path, ledger_path, checkpoint_path = _valid_wall_clock_artifacts(tmp_path)
    result = phase.run_p150_qualification(
        predecessor_path=_write_p149_release_evidence(tmp_path),
        fast_schedule=_fast_schedule(),
        wall_clock_result=wall_clock,
        wall_clock_result_path=result_path,
        wall_clock_ledger_path=ledger_path,
        wall_clock_checkpoint_path=checkpoint_path,
        output_dir=tmp_path,
        evidence_mode="isolated_test",
    )
    report = phase.validate_p150_report(result["report"])
    manifest = phase.validate_p150_freeze_manifest(result["freeze_manifest"])
    review = phase.validate_p150_final_review(_p150_final_review(report, manifest), report=report, freeze_manifest=manifest)
    wall_clock_evidence = phase.build_p150_wall_clock_evidence(
        wall_clock,
        result_path=result_path,
        ledger_path=ledger_path,
        checkpoint_path=checkpoint_path,
        allow_injected_test_clock=True,
    )
    assembled = phase.assemble_release_evidence(
        contract=phase.P150_CONTRACT,
        report=report,
        freeze_manifest=manifest,
        final_review=review,
    )
    assembled["wall_clock_evidence"] = wall_clock_evidence
    assembled["evidence_hash"] = _stable_hash({key: value for key, value in assembled.items() if key != "evidence_hash"})

    with pytest.raises(Exception, match="complete|raw|path"):
        phase.validate_p150_release_evidence(assembled, wall_clock_result_path=result_path)

    canonical_result = tmp_path / phase.CANONICAL_WALL_CLOCK_RESULT_PATH
    canonical_ledger = tmp_path / phase.CANONICAL_WALL_CLOCK_LEDGER_PATH
    canonical_checkpoint = tmp_path / phase.CANONICAL_WALL_CLOCK_CHECKPOINT_PATH
    canonical_result.parent.mkdir(parents=True, exist_ok=True)
    canonical_ledger.write_bytes(ledger_path.read_bytes())
    canonical_checkpoint.write_bytes(checkpoint_path.read_bytes())
    canonical_receipt = copy.deepcopy(wall_clock)
    canonical_receipt["ledger"] = dict(canonical_receipt["ledger"], path=str(canonical_ledger))
    canonical_receipt["receipt_hash"] = _stable_hash(
        {key: value for key, value in canonical_receipt.items() if key != "receipt_hash"}
    )
    canonical_result.write_text(
        json.dumps(canonical_receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    canonical_evidence = phase.build_p150_wall_clock_evidence(
        canonical_receipt,
        result_path=canonical_result,
        ledger_path=canonical_ledger,
        checkpoint_path=canonical_checkpoint,
        allow_injected_test_clock=True,
    )
    canonical_assembled = copy.deepcopy(assembled)
    canonical_assembled["wall_clock_evidence"] = canonical_evidence
    canonical_assembled["metrics"]["wall_clock_evidence_hash"] = _stable_hash(canonical_evidence)
    canonical_assembled["evidence_hash"] = _stable_hash(
        {key: value for key, value in canonical_assembled.items() if key != "evidence_hash"}
    )
    with pytest.raises(Exception, match="real|runner|clock|evidence"):
        phase.validate_p150_release_evidence(canonical_assembled, project_root=tmp_path)
    with pytest.raises(Exception, match="real|runner|clock|evidence"):
        phase.assemble_p150_release_evidence_from_paths(
            report=report,
            freeze_manifest=manifest,
            final_review=review,
            project_root=tmp_path,
        )

    clock = _FakeMonotonicClock()
    with pytest.raises(Exception, match="clock|sleeper|required"):
        phase.run_wall_clock_runner(output_dir=tmp_path / "partial-injection", clock_ns=clock.monotonic_ns)
    with pytest.raises(Exception, match="cycle|invalid"):
        phase.generate_injected_wall_clock_artifacts(
            output_dir=tmp_path / "invalid-cycle-count",
            resume=False,
            clock_ns=clock.monotonic_ns,
            sleeper=clock.sleep,
            test_only_cycle_count=-1,
        )
