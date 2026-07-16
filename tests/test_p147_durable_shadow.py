from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash

ROOT = Path(__file__).resolve().parents[1]

FROZEN_COUNTER_KEYS = {
    "read_attempt_count",
    "read_success_count",
    "model_call_count",
    "external_model_call_count",
    "investigation_tool_call_count",
    "action_intent_count",
    "action_commit_count",
    "action_execution_count",
    "rollback_count",
    "heartbeat_count",
    "deadman_count",
    "artifact_write_count",
    "credential_read_count",
    "external_network_count",
    "external_message_count",
    "shell_count",
    "staging_mutation_count",
    "production_mutation_count",
    "authority_escape_count",
}

P147_LIMITATIONS = [
    "credential_free_no_external_network",
    "no_model_action_or_mutation",
    "offline_injected_provider_shapes_only_no_oa3_or_live_staging",
]

P147_CASE_IDS = [
    "prometheus_ok",
    "loki_jsonl_ok",
    "sentry_style_ok",
    "trace_fixture_ok",
    "deployment_history_ok",
    "restart_resume",
    "deadman_30s",
    "provider_faults",
]


def _p147() -> Any:
    from app.services import p147_durable_shadow

    return p147_durable_shadow


def _counter_template(**overrides: int) -> dict[str, int]:
    counters = {key: 0 for key in FROZEN_COUNTER_KEYS}
    counters.update(overrides)
    return counters


def _with_self_hash(payload: dict[str, Any], field: str) -> dict[str, Any]:
    sealed = deepcopy(payload)
    sealed[field] = stable_hash({key: value for key, value in sealed.items() if key != field})
    return sealed


def _p146_predecessor() -> dict[str, Any]:
    from app.services.p147_p152_contracts import predecessor_from_path

    return predecessor_from_path(ROOT, _p147().P147_CONTRACT.predecessors[0])


def _provider_profile() -> dict[str, Any]:
    return {
        "schema_version": "p147.release_profile.v1",
        "phase": "p147",
        "case_ids": sorted(P147_CASE_IDS),
        "limits": {
            "provider_reads_per_cycle": 5,
            "investigation_calls_per_cycle": 3,
            "retries": 2,
            "timeout_seconds": 2,
            "query_window_seconds": 300,
            "response_bytes": 1_048_576,
            "normalized_records_per_cycle": 10_000,
            "deadman_missed_seconds": 30,
        },
    }


def _provider_fixtures() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "prometheus_ok",
            "provider_kind": "prometheus",
            "operation": "GET",
            "target": "fixture://prometheus/range",
            "records": [{"metric": "checkout_error_rate_bps", "value": 125, "ts": 1000}],
        },
        {
            "case_id": "loki_jsonl_ok",
            "provider_kind": "loki_jsonl",
            "operation": "GET",
            "target": "fixture://loki/streams",
            "records": [{"line": "checkout recovered", "ts": 1001}],
        },
        {
            "case_id": "sentry_style_ok",
            "provider_kind": "sentry_style",
            "operation": "GET",
            "target": "fixture://sentry/issues",
            "records": [{"issue": "CHECKOUT-7", "fingerprint": "redacted"}],
        },
        {
            "case_id": "trace_fixture_ok",
            "provider_kind": "trace",
            "operation": "GET",
            "target": "fixture://trace/spans",
            "records": [{"trace_id": "0" * 32, "span_id": "1" * 16, "parent_id": ""}],
        },
        {
            "case_id": "deployment_history_ok",
            "provider_kind": "deployment_history",
            "operation": "GET",
            "target": "fixture://deployments/history",
            "records": [{"deployment": "checkout-api", "version": "2026.07.16.1"}],
        },
        {
            "case_id": "restart_resume",
            "provider_kind": "state",
            "operation": "GET",
            "target": "fixture://state/checkpoint",
            "records": [{"cursor": "cursor-after-checkpoint", "heartbeat_epoch": 1, "dedupe_key": "checkpoint-1"}],
        },
        {
            "case_id": "deadman_30s",
            "provider_kind": "state",
            "operation": "GET",
            "target": "fixture://state/heartbeat",
            "records": [{"heartbeat_age_seconds": 31}],
        },
        {
            "case_id": "provider_faults",
            "provider_kind": "prometheus",
            "operation": "POST",
            "target": "fixture://prometheus/range",
            "records": [],
        },
    ]


def test_contract_and_predecessor_fail_closed(tmp_path: Path) -> None:
    p147 = _p147()
    from app.services.p147_p152_contracts import ContractError, _validate_p146_release_evidence, load_json, with_self_hash

    forged_p146 = load_json(ROOT / "evals/p146/final/release-evidence.json")
    forged_p146["limitations"] = ["forged"]
    forged_p146 = with_self_hash(forged_p146, "evidence_hash")
    with pytest.raises(ContractError, match="p146_full_release_invalid"):
        _validate_p146_release_evidence(ROOT, forged_p146)

    forged_predecessor = _p146_predecessor()
    forged_predecessor["required_status"] = "p146_preliminary_shadow_ready"

    with pytest.raises(ValueError, match="predecessor|p146|status|release"):
        p147.run_p147_qualification(
            project_root=ROOT,
            output_dir=tmp_path,
            profile=_provider_profile(),
            predecessor=forged_predecessor,
            provider_fixtures=_provider_fixtures(),
        )

    missing_hash = _p146_predecessor()
    del missing_hash["evidence_hash"]
    with pytest.raises(ValueError, match="predecessor|field|hash"):
        p147.validate_p147_report(
            {
                "schema_version": "p147.report.v1",
                "phase": "p147",
                "status": "p147_durable_provider_shadow_qualified",
                "claim": "provider-shaped conformance",
                "limitations": P147_LIMITATIONS,
                "profile_hash": "sha256:" + "3" * 64,
                "predecessors": [missing_hash],
                "source_hashes": {"app/services/p147_durable_shadow.py": "sha256:" + "4" * 64},
                "case_count": 8,
                "passed": 8,
                "failed": 0,
                "metrics": {
                    "provider_read_count": 5,
                    "normalized_record_count": 5,
                    "resumed_cursor_count": 1,
                    "heartbeat_count": 1,
                    "deadman_count": 1,
                    "investigation_tool_call_count": 3,
                },
                "counters": _counter_template(),
                "rows": [],
                "report_hash": "sha256:" + "5" * 64,
            }
        )

    minimal_release = {
        "schema_version": "p147.release_evidence.v1",
        "phase": "p147",
        "status": "p147_durable_provider_shadow_qualified",
        "evidence_hash": "sha256:" + "9" * 64,
    }
    from app.services.p147_p152_contracts import PredecessorSpec, predecessor_from_release_evidence

    with pytest.raises(ValueError, match="release.*keyset|minimal|predecessor"):
        predecessor_from_release_evidence(
            minimal_release,
            PredecessorSpec(
                phase="p147",
                path="evals/p147/output/release-evidence.json",
                schema_version="p147.release_evidence.v1",
                status="p147_durable_provider_shadow_qualified",
            ),
        )


def test_happy_path_report_and_counters(tmp_path: Path) -> None:
    p147 = _p147()

    report = p147.run_p147_qualification(
        project_root=ROOT,
        output_dir=tmp_path,
        profile=_provider_profile(),
        predecessor=_p146_predecessor(),
        provider_fixtures=_provider_fixtures(),
    )

    assert p147.validate_p147_report(report) == report
    assert report["schema_version"] == "p147.report.v1"
    assert report["status"] == "p147_durable_provider_shadow_qualified"
    assert report["limitations"] == P147_LIMITATIONS
    assert report["case_count"] == 8
    assert report["passed"] == 8
    assert report["failed"] == 0
    assert set(report["counters"]) == FROZEN_COUNTER_KEYS
    assert report["counters"]["read_attempt_count"] <= 5
    assert report["counters"]["read_success_count"] == 5
    assert report["counters"]["investigation_tool_call_count"] <= 3
    assert report["counters"]["external_network_count"] == 0
    assert report["counters"]["credential_read_count"] == 0
    assert report["counters"]["model_call_count"] == 0
    assert report["counters"]["action_execution_count"] == 0
    assert report["metrics"] == {
        "provider_read_count": 5,
        "normalized_record_count": 5,
        "resumed_cursor_count": 1,
        "heartbeat_count": 1,
        "deadman_count": 1,
        "investigation_tool_call_count": 3,
    }
    assert [row["case_id"] for row in report["rows"]] == sorted(P147_CASE_IDS)
    assert (tmp_path / "durable-state.json").is_file()
    for row in report["rows"]:
        assert row["expected"]["schema_version"] == "p147.row_result.v1"
        assert row["observed"]["measurements"]["provider_kind"] in {
            "prometheus",
            "loki_jsonl",
            "sentry_style",
            "trace",
            "deployment_history",
            "state",
            "fault",
        }


def test_fault_matrix_and_recovery(tmp_path: Path) -> None:
    p147 = _p147()

    report = p147.run_p147_qualification(
        project_root=ROOT,
        output_dir=tmp_path,
        profile=_provider_profile(),
        predecessor=_p146_predecessor(),
        provider_fixtures=_provider_fixtures(),
    )

    rows = {row["case_id"]: row for row in report["rows"]}
    assert rows["restart_resume"]["observed"]["measurements"]["resume_count"] == 1
    assert rows["deadman_30s"]["observed"]["measurements"]["deadman_count"] == 1
    assert "non_get_provider_operation" in rows["provider_faults"]["observed"]["reason_codes"]
    assert report["counters"]["heartbeat_count"] >= 1
    assert report["counters"]["deadman_count"] == 1
    assert report["counters"]["read_attempt_count"] <= 5

    state_path = tmp_path / "durable-state.json"
    final_state = p147._validate_durable_state(json.loads(state_path.read_text(encoding="utf-8")))
    assert final_state["generation"] == 2
    assert final_state["cursor"] == "cursor-after-checkpoint"
    with pytest.raises(ValueError, match="corrupt|truncated"):
        (tmp_path / "truncated-state.json").write_text("{", encoding="utf-8")
        p147._load_durable_state(tmp_path / "truncated-state.json", expected_parent_hash="sha256:" + "0" * 64, seen_hashes=set())
    with pytest.raises(ValueError, match="forked"):
        p147._load_durable_state(state_path, expected_parent_hash="sha256:" + "1" * 64, seen_hashes=set())
    with pytest.raises(ValueError, match="replay"):
        p147._load_durable_state(state_path, expected_parent_hash=final_state["parent_hash"], seen_hashes={final_state["state_hash"]})
    stale_path = tmp_path / "stale-state.json"
    p147._write_durable_state(
        stale_path,
        generation=3,
        parent_hash="sha256:" + "0" * 64,
        cursor="cursor-after-checkpoint",
        heartbeat_epoch=1,
        dedupe_keys=["checkpoint-1"],
    )
    with pytest.raises(ValueError, match="stale"):
        p147._load_durable_state(stale_path, expected_parent_hash="sha256:" + "0" * 64, seen_hashes=set())


def test_forgery_and_authority_rejected(tmp_path: Path) -> None:
    p147 = _p147()

    forged_provider = deepcopy(_provider_fixtures()[0])
    forged_provider["operation"] = "POST"
    forged_fixtures = _provider_fixtures()
    forged_fixtures[0] = forged_provider
    with pytest.raises(ValueError, match="read_only|non_get|mutation"):
        p147.run_p147_qualification(
            project_root=ROOT,
            output_dir=tmp_path,
            profile=_provider_profile(),
            predecessor=_p146_predecessor(),
            provider_fixtures=forged_fixtures,
        )

    forged_report = {
        "schema_version": "p147.report.v1",
        "phase": "p147",
        "status": "p147_durable_provider_shadow_qualified",
        "claim": "provider-shaped conformance",
        "limitations": P147_LIMITATIONS,
        "profile_hash": "sha256:" + "3" * 64,
        "predecessors": [_p146_predecessor()],
        "source_hashes": {"app/services/p147_durable_shadow.py": "sha256:" + "4" * 64},
        "case_count": 8,
        "passed": 8,
        "failed": 0,
        "metrics": {},
        "counters": _counter_template(external_network_count=1, authority_escape_count=1),
        "rows": [],
        "report_hash": "sha256:" + "5" * 64,
    }
    with pytest.raises(ValueError, match="counter|external_network_count|authority_escape_count|zero"):
        p147.validate_p147_report(forged_report)


def test_release_evidence_requires_zero_finding_review(tmp_path: Path) -> None:
    p147 = _p147()

    report = p147.run_p147_qualification(
        project_root=ROOT,
        output_dir=tmp_path,
        profile=_provider_profile(),
        predecessor=_p146_predecessor(),
        provider_fixtures=_provider_fixtures(),
    )
    freeze_payload = {
        "schema_version": "p147.freeze_manifest.v1",
        "phase": "p147",
        "plan_hash": report["source_hashes"]["docs/operations/p147-p152-program-plan.md"],
        "test_spec_hash": report["source_hashes"]["docs/operations/p147-test-spec.md"],
        "source_hashes": report["source_hashes"],
        "profile_hash": report["profile_hash"],
        "predecessor_file_hashes": [report["predecessors"][0]["file_hash"]],
        "report_hash": report["report_hash"],
        "manifest_hash": "",
    }
    freeze = p147.validate_p147_freeze_manifest(_with_self_hash(freeze_payload, "manifest_hash"))
    review = _with_self_hash(
        {
        "schema_version": "p147.final_review.v1",
        "phase": "p147",
        "writer_agent_id": "019f72f0-0000-7000-8000-000000000047",
        "reviewer_identity": "independent-p147-reviewer",
        "reviewer_agent_id": "019f72f0-0000-7000-8000-000000000147",
        "reviewed_at": "2026-07-16T00:00:00Z",
        "decision": "approve",
        "findings": {"p0": 0, "p1": 1, "p2": 0, "p3": 0},
        "limitations": P147_LIMITATIONS,
        "reviewed_report_hash": report["report_hash"],
        "reviewed_manifest_hash": freeze["manifest_hash"],
        "review_hash": "",
        },
        "review_hash",
    )

    with pytest.raises(ValueError, match="review|findings|p1|zero"):
        p147.validate_p147_final_review(review, report=report, freeze_manifest=freeze)

    review["findings"]["p1"] = 0
    review = _with_self_hash(review, "review_hash")
    accepted_review = p147.validate_p147_final_review(review, report=report, freeze_manifest=freeze)
    evidence_payload = {
            "schema_version": "p147.release_evidence.v1",
            "phase": "p147",
            "status": "p147_durable_provider_shadow_qualified",
            "claim": report["claim"],
            "limitations": P147_LIMITATIONS,
            "report_hash": report["report_hash"],
            "freeze_hash": freeze["manifest_hash"],
            "review_hash": accepted_review["review_hash"],
            "predecessors": report["predecessors"],
            "source_hashes": report["source_hashes"],
            "metrics": report["metrics"],
            "counters": report["counters"],
            "passed": 8,
            "failed": 0,
            "evidence_hash": "",
    }
    evidence = p147.validate_p147_release_evidence(_with_self_hash(evidence_payload, "evidence_hash"))
    assert evidence["status"] == "p147_durable_provider_shadow_qualified"
