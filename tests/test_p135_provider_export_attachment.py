from __future__ import annotations

import hashlib
import json
import os
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p120_governance import zero_authority_counters as zero_p120_authority
from app.services.p120_normalization import validate_normalized_record
from app.services.p121_signals import zero_authority_counters as zero_p121_authority
from app.services.p134_observation_authority import (
    build_contract,
    build_contract_core,
    build_proposal,
    build_review_receipt,
    evaluate_proposal,
)
from app.services.p134_observation_authority import (
    new_receipt_ledger as new_p134_receipt_ledger,
)
from app.services.p135_provider_export_attachment import (
    P135ExportError,
    attach_export,
    build_export_manifest,
    new_execution_ledger,
    validate_denominator_failure_bundle,
    validate_execution_ledger,
    validate_export_manifest,
    validate_normalized_bundle,
    zero_forbidden_authority,
    zero_observation_activity,
)

FIXTURE_ROOT = Path("evals/p135/input/exports")
STARTED_AT = "2026-07-13T00:10:00Z"
COMPLETED_AT = "2026-07-13T00:10:01Z"

PROVIDER_CASES: tuple[dict[str, str], ...] = (
    {
        "source_id": "grafana-dashboard",
        "provider": "grafana",
        "format": "grafana.dashboard.classic.v1",
        "signal_family": "topology",
        "capability": "telemetry.topology.read",
        "fixture": "grafana_dashboard.json",
    },
    {
        "source_id": "loki-streams",
        "provider": "loki",
        "format": "loki.query_range.streams.v1",
        "signal_family": "logs",
        "capability": "telemetry.logs.read",
        "fixture": "loki_streams.json",
    },
    {
        "source_id": "otlp-metrics",
        "provider": "opentelemetry",
        "format": "otlp.file.jsonl.v1",
        "signal_family": "metrics",
        "capability": "telemetry.metrics.read",
        "fixture": "otlp_metrics.jsonl",
    },
    {
        "source_id": "prometheus-matrix",
        "provider": "prometheus",
        "format": "prometheus.query_range.matrix.v1",
        "signal_family": "metrics",
        "capability": "telemetry.metrics.read",
        "fixture": "prometheus_matrix.json",
    },
    {
        "source_id": "sentry-issues",
        "provider": "sentry",
        "format": "sentry.issues.api.list.v1",
        "signal_family": "events",
        "capability": "telemetry.events.read",
        "fixture": "sentry_issues.json",
    },
)


def _budgets(**overrides: int) -> dict[str, int]:
    values = {
        "window_seconds": 3600,
        "max_allowed_requests_per_window": 16,
        "max_allowed_estimated_response_bytes_per_window": 1_000_000,
        "max_allowed_estimated_records_per_window": 10_000,
        "max_unique_hosts_per_window": 3,
        "max_unique_methods_per_window": 1,
        "max_unique_capabilities_per_window": 6,
        "max_single_response_bytes": 100_000,
        "max_timeout_ms": 5_000,
        "max_attempt_number": 1,
    }
    values.update(overrides)
    return values


def _contract() -> dict[str, Any]:
    core = build_contract_core(
        {
            "contract_id": "p135-local-export-attachment",
            "contract_version": 1,
            "subject_ref_hash": stable_hash({"subject": "p135-fixtures"}),
            "max_authority_level": "OA1_LOCAL_ARTIFACT",
            "allowed_hosts": ["local-artifact.telemetry-read"],
            "allowed_methods": ["LOCAL_READ_FILE"],
            "allowed_capabilities": [
                "telemetry.events.read",
                "telemetry.logs.read",
                "telemetry.metrics.read",
                "telemetry.topology.read",
                "telemetry.traces.read",
            ],
            "budgets": _budgets(),
            "valid_from": "2026-07-13T00:00:00Z",
            "expires_at": "2026-07-14T00:00:00Z",
            "default_decision": "deny",
            "kill_switch": False,
            "action_authority": zero_p121_authority(),
        }
    )
    review = build_review_receipt(
        core,
        {
            "decision": "approve",
            "reviewer_ref_hash": stable_hash({"reviewer": "p135-independent-reviewer"}),
            "reviewed_at": "2026-07-13T00:00:01Z",
            "expires_at": "2026-07-13T23:59:59Z",
        },
    )
    return build_contract(core, review)


def _copy_fixture_tree(tmp_path: Path) -> Path:
    root = tmp_path / "exports"
    root.mkdir()
    for case in PROVIDER_CASES:
        shutil.copyfile(FIXTURE_ROOT / case["fixture"], root / case["fixture"])
    shutil.copyfile(FIXTURE_ROOT / "p120_wrapped_prompt_secret.json", root / "p120_wrapped_prompt_secret.json")
    shutil.copyfile(FIXTURE_ROOT / "parser_failure_duplicate_key.json", root / "parser_failure_duplicate_key.json")
    shutil.copyfile(FIXTURE_ROOT / "prometheus_wrong_result_type.json", root / "prometheus_wrong_result_type.json")
    return root


def _artifact_input(case: dict[str, str], *, relative_path: str | None = None) -> dict[str, Any]:
    path = FIXTURE_ROOT / case["fixture"]
    content = path.read_bytes()
    return {
        "source_id": case["source_id"],
        "provider": case["provider"],
        "format": case["format"],
        "signal_family": case["signal_family"],
        "relative_path": relative_path or case["fixture"],
        "expected_content_hash": "sha256:" + hashlib.sha256(content).hexdigest(),
        "expected_bytes": len(content),
        "expected_records": 2 if case["provider"] in {"prometheus", "loki"} else 1,
        "authority_capability": case["capability"],
        "authority_source_ref_hash": stable_hash({"p135_source_id": case["source_id"]}),
    }


def _manifest_data(*artifacts: dict[str, Any], root_ref_hash: str | None = None) -> dict[str, Any]:
    return {
        "manifest_id": "p135-provider-export-fixture",
        "manifest_version": 1,
        "created_at": "2026-07-13T00:05:00Z",
        "root_ref_hash": root_ref_hash or stable_hash({"root": "tmp-p135-fixtures"}),
        "limits": {
            "max_artifacts": 16,
            "max_file_bytes": 100_000,
            "max_total_bytes": 1_000_000,
            "max_records_per_artifact": 100,
            "max_total_records": 1_000,
            "max_json_depth": 32,
            "max_json_nodes": 20_000,
            "max_string_bytes": 4096,
            "max_preview_bytes": 96,
            "max_attributes_per_record": 32,
            "max_line_bytes": 8192,
        },
        "artifacts": list(artifacts),
    }


def _authority_receipts(contract: dict[str, Any], artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ledger = new_p134_receipt_ledger(contract, window_started_at="2026-07-13T00:00:00Z")
    receipts: list[dict[str, Any]] = []
    for index, artifact in enumerate(artifacts, start=1):
        proposal = build_proposal(
            {
                "request_id": f"p135-local-{index}",
                "sequence": index,
                "proposed_at": f"2026-07-13T00:{index:02d}:00Z",
                "requested_level": "OA1_LOCAL_ARTIFACT",
                "source_ref_hash": artifact["authority_source_ref_hash"],
                "host_label": "local-artifact.telemetry-read",
                "method": "LOCAL_READ_FILE",
                "capability": artifact["authority_capability"],
                "estimated_response_bytes": artifact["expected_bytes"],
                "estimated_records": artifact["expected_records"],
                "timeout_ms": 1000,
                "attempt_number": 1,
            }
        )
        result = evaluate_proposal(contract, proposal, ledger)
        assert result.receipt["decision"] == "allowed"
        receipts.append(result.receipt)
        ledger = result.ledger
    return receipts


def _manifest_for_cases(*cases: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    contract = _contract()
    artifacts = [_artifact_input(case) for case in cases]
    receipts = _authority_receipts(contract, artifacts)
    manifest = build_export_manifest(_manifest_data(*artifacts), contract, receipts)
    validate_export_manifest(manifest, contract, receipts)
    return manifest, contract, receipts


def _attach(
    root: Path,
    manifest: dict[str, Any],
    source_id: str,
    contract: dict[str, Any],
    receipts: list[dict[str, Any]],
    ledger: dict[str, Any] | None = None,
) -> Any:
    return attach_export(
        root,
        manifest,
        source_id,
        contract,
        receipts,
        ledger or new_execution_ledger(manifest),
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )


@pytest.mark.parametrize("case", PROVIDER_CASES, ids=[case["provider"] for case in PROVIDER_CASES])
def test_attaches_valid_provider_fixture_and_validates_bundle_and_ledger(tmp_path: Path, case: dict[str, str]) -> None:
    root = _copy_fixture_tree(tmp_path)
    manifest, contract, receipts = _manifest_for_cases(case)

    result = _attach(root, manifest, case["source_id"], contract, receipts)

    assert result.duplicate is False
    validate_normalized_bundle(result.bundle)
    validate_execution_ledger(result.ledger, manifest, contract, receipts)
    assert result.receipt["source_id"] == case["source_id"]
    assert result.bundle["provider"] == case["provider"]
    assert result.activity["local_file_read_count"] == 1
    assert result.receipt["authority_counters"] == zero_forbidden_authority()


def test_build_export_manifest_requires_strict_schema_and_canonical_hash() -> None:
    contract = _contract()
    artifact = _artifact_input(PROVIDER_CASES[3])
    receipts = _authority_receipts(contract, [artifact])
    manifest = build_export_manifest(_manifest_data(artifact), contract, receipts)

    assert manifest["schema_version"] == "p135.export_manifest.v1"
    assert [item["source_id"] for item in manifest["artifacts"]] == sorted(
        item["source_id"] for item in manifest["artifacts"]
    )
    assert manifest["manifest_hash"] == stable_hash(
        {key: value for key, value in manifest.items() if key != "manifest_hash"}
    )
    with pytest.raises(P135ExportError, match="unexpected_manifest_field"):
        validate_export_manifest({**manifest, "extra": "field"}, contract, receipts)


def test_export_manifest_rejects_boolean_limits() -> None:
    contract = _contract()
    artifact = _artifact_input(PROVIDER_CASES[3])
    receipts = _authority_receipts(contract, [artifact])
    data = _manifest_data(artifact)
    data["limits"]["max_artifacts"] = True

    with pytest.raises(P135ExportError, match="invalid_limit:max_artifacts"):
        build_export_manifest(data, contract, receipts)


def test_wrong_or_denied_p134_authority_blocks_before_read(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = _copy_fixture_tree(tmp_path)
    contract = _contract()
    artifact = _artifact_input(PROVIDER_CASES[3])
    wrong_capability = {**artifact, "authority_capability": "telemetry.logs.read"}
    receipts = _authority_receipts(contract, [wrong_capability])
    manifest = build_export_manifest(_manifest_data(artifact), contract, receipts)

    def fail_read(*_args: Any, **_kwargs: Any) -> bytes:
        raise AssertionError("P135 read before validating P134 authority")

    monkeypatch.setattr(Path, "read_bytes", fail_read)
    with pytest.raises(P135ExportError, match="authority_capability_mismatch"):
        _attach(root, manifest, artifact["source_id"], contract, receipts)


@pytest.mark.parametrize(
    ("relative_path", "reason"),
    [
        ("../prometheus_matrix.json", "unsafe_relative_path"),
        ("/tmp/prometheus_matrix.json", "unsafe_relative_path"),
        ("nested/../prometheus_matrix.json", "unsafe_relative_path"),
        ("secret-token/prometheus_matrix.json", "credential_shaped_path"),
    ],
)
def test_export_manifest_rejects_unsafe_paths(relative_path: str, reason: str) -> None:
    contract = _contract()
    artifact = _artifact_input(PROVIDER_CASES[3], relative_path=relative_path)
    receipts = _authority_receipts(contract, [artifact])

    with pytest.raises(P135ExportError, match=reason):
        build_export_manifest(_manifest_data(artifact), contract, receipts)


def test_attach_rejects_symlink_hardlink_and_nonregular_files(tmp_path: Path) -> None:
    root = tmp_path / "exports"
    root.mkdir()
    real = root / "real.json"
    shutil.copyfile(FIXTURE_ROOT / "prometheus_matrix.json", real)
    symlink = root / "symlink.json"
    symlink.symlink_to(real.name)
    hardlink = root / "hardlink.json"
    os.link(real, hardlink)
    directory = root / "directory.json"
    directory.mkdir()

    contract = _contract()
    for relative_path, reason in [
        ("symlink.json", "symlink_rejected"),
        ("hardlink.json", "hardlink_rejected"),
        ("directory.json", "nonregular_file"),
    ]:
        artifact = _artifact_input(PROVIDER_CASES[3], relative_path=relative_path)
        receipts = _authority_receipts(contract, [artifact])
        manifest = build_export_manifest(_manifest_data(artifact), contract, receipts)
        with pytest.raises(P135ExportError, match=reason):
            _attach(root, manifest, artifact["source_id"], contract, receipts)


def test_attach_rejects_intermediate_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "exports"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    shutil.copyfile(FIXTURE_ROOT / "prometheus_matrix.json", outside / "prometheus_matrix.json")
    (root / "escape").symlink_to(outside, target_is_directory=True)
    contract = _contract()
    artifact = _artifact_input(PROVIDER_CASES[3], relative_path="escape/prometheus_matrix.json")
    receipts = _authority_receipts(contract, [artifact])
    manifest = build_export_manifest(_manifest_data(artifact), contract, receipts)

    with pytest.raises(P135ExportError, match="symlink_rejected"):
        _attach(root, manifest, artifact["source_id"], contract, receipts)


def test_attach_rejects_content_hash_and_size_mismatch(tmp_path: Path) -> None:
    root = _copy_fixture_tree(tmp_path)
    manifest, contract, receipts = _manifest_for_cases(PROVIDER_CASES[3])
    (root / "prometheus_matrix.json").write_text('{"status":"success","data":{"resultType":"matrix","result":[]}}', encoding="utf-8")

    with pytest.raises(P135ExportError, match="content_hash_mismatch|file_size_mismatch"):
        _attach(root, manifest, "prometheus-matrix", contract, receipts)


def test_duplicate_reattachment_rereads_current_bytes_and_keeps_success_ledger_immutable(tmp_path: Path) -> None:
    root = _copy_fixture_tree(tmp_path)
    manifest, contract, receipts = _manifest_for_cases(PROVIDER_CASES[3])
    first = _attach(root, manifest, "prometheus-matrix", contract, receipts)

    duplicate = _attach(root, manifest, "prometheus-matrix", contract, receipts, first.ledger)

    assert duplicate.duplicate is True
    assert duplicate.receipt == first.receipt
    assert duplicate.ledger == first.ledger
    assert duplicate.activity["duplicate_validation_read_count"] == 1
    assert duplicate.activity["local_file_read_count"] == 1


def test_success_records_wrap_independently_valid_denominator_visible_p120_records(tmp_path: Path) -> None:
    root = _copy_fixture_tree(tmp_path)
    manifest, contract, receipts = _manifest_for_cases(PROVIDER_CASES[3])
    result = _attach(root, manifest, "prometheus-matrix", contract, receipts)

    for record in result.bundle["records"]:
        validate_normalized_record(record["p120_record"])
        assert record["p120_record"]["denominator_visible"] is True
        assert record["p120_record"]["authority_counters"] == zero_p120_authority()


def test_prompt_injection_and_secret_text_are_flagged_and_redacted(tmp_path: Path) -> None:
    root = _copy_fixture_tree(tmp_path)
    case = {
        **PROVIDER_CASES[3],
        "source_id": "prompt-secret",
        "fixture": "p120_wrapped_prompt_secret.json",
    }
    manifest, contract, receipts = _manifest_for_cases(case)
    result = _attach(root, manifest, "prompt-secret", contract, receipts)

    serialized = json.dumps(result.bundle, sort_keys=True)
    assert "sk_live_secret" not in serialized
    assert "api_key" not in serialized
    assert "ignore previous instructions" not in serialized
    assert any({"prompt_like_text", "credential_like_text"} <= set(record["risk_flags"]) for record in result.bundle["records"])


def test_parser_failure_after_content_read_returns_denominator_visible_failure_bundle(tmp_path: Path) -> None:
    root = _copy_fixture_tree(tmp_path)
    case = {
        **PROVIDER_CASES[3],
        "source_id": "duplicate-key-failure",
        "fixture": "parser_failure_duplicate_key.json",
    }
    manifest, contract, receipts = _manifest_for_cases(case)
    result = _attach(root, manifest, "duplicate-key-failure", contract, receipts)

    validate_denominator_failure_bundle(result.bundle)
    assert result.bundle["schema_version"] == "p135.denominator_failure_bundle.v1"
    assert result.receipt["status"] == "failed"
    assert result.activity["local_bytes_read"] > 0
    for record in result.bundle["records"]:
        validate_normalized_record(record["p120_record"])
        assert record["p120_record"]["evidence_state"] == "fail_closed"
        assert record["p120_record"]["denominator_visible"] is True


def test_provider_parser_failures_are_denominator_visible_not_promoted_successes(tmp_path: Path) -> None:
    root = _copy_fixture_tree(tmp_path)
    case = {
        **PROVIDER_CASES[3],
        "source_id": "wrong-result-type",
        "fixture": "prometheus_wrong_result_type.json",
    }
    manifest, contract, receipts = _manifest_for_cases(case)
    result = _attach(root, manifest, "wrong-result-type", contract, receipts)

    validate_denominator_failure_bundle(result.bundle)
    assert result.receipt["status"] == "failed"
    assert result.bundle["records"][0]["p120_record"]["denominator_visible"] is True


def test_bundle_counter_and_hash_tamper_are_rejected(tmp_path: Path) -> None:
    root = _copy_fixture_tree(tmp_path)
    manifest, contract, receipts = _manifest_for_cases(PROVIDER_CASES[3])
    result = _attach(root, manifest, "prometheus-matrix", contract, receipts)

    forged_bundle = deepcopy(result.bundle)
    forged_bundle["record_count"] += 1
    forged_bundle["bundle_hash"] = stable_hash({key: value for key, value in forged_bundle.items() if key != "bundle_hash"})
    with pytest.raises(P135ExportError, match="bundle_record_count_mismatch"):
        validate_normalized_bundle(forged_bundle)

    forged_ledger = deepcopy(result.ledger)
    forged_ledger["counters"]["local_bytes_read"] += 1
    forged_ledger["ledger_hash"] = stable_hash({key: value for key, value in forged_ledger.items() if key != "ledger_hash"})
    with pytest.raises(P135ExportError, match="ledger_counter_mismatch"):
        validate_execution_ledger(forged_ledger, manifest, contract, receipts)

    forged_receipt_id = deepcopy(result.ledger)
    forged_receipt_id["receipts"][0]["receipt_id"] = stable_hash({"forged": "receipt-id"})
    forged_receipt_id["receipts"][0]["receipt_hash"] = stable_hash(
        {key: value for key, value in forged_receipt_id["receipts"][0].items() if key != "receipt_hash"}
    )
    forged_receipt_id["ledger_hash"] = stable_hash(
        {key: value for key, value in forged_receipt_id.items() if key != "ledger_hash"}
    )
    with pytest.raises(P135ExportError, match="receipt_id_mismatch"):
        validate_execution_ledger(forged_receipt_id, manifest, contract, receipts)

    forged_bundle_ref = deepcopy(result.ledger)
    forged_bundle_ref["receipts"][0]["normalized_bundle_hash"] = "not-a-sha256"
    forged_bundle_ref["receipts"][0]["receipt_hash"] = stable_hash(
        {key: value for key, value in forged_bundle_ref["receipts"][0].items() if key != "receipt_hash"}
    )
    forged_bundle_ref["ledger_hash"] = stable_hash(
        {key: value for key, value in forged_bundle_ref.items() if key != "ledger_hash"}
    )
    with pytest.raises(P135ExportError, match="invalid_normalized_bundle_hash"):
        validate_execution_ledger(forged_bundle_ref, manifest, contract, receipts)

    forged_receipt_bundle = deepcopy(result.bundle)
    forged_receipt_bundle["artifact_bytes"] += 1
    forged_receipt_bundle["bundle_hash"] = stable_hash(
        {key: value for key, value in forged_receipt_bundle.items() if key != "bundle_hash"}
    )
    with pytest.raises(P135ExportError, match="receipt_bundle_hash_mismatch"):
        validate_execution_ledger(result.ledger, manifest, contract, receipts, bundles=[forged_receipt_bundle])


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("source_record_hash", "record_source_hash_mismatch"),
        ("evidence_id", "record_evidence_id_mismatch"),
        ("content_hash", "record_content_hash_mismatch"),
        ("provider", "record_provider_mismatch"),
        ("format", "record_format_mismatch"),
        ("p120_source_id", "record_source_id_mismatch"),
        ("execution_receipt_ref", "invalid_execution_receipt_ref"),
    ],
)
def test_rehashed_record_semantic_tamper_is_rejected(
    tmp_path: Path,
    mutation: str,
    reason: str,
) -> None:
    root = _copy_fixture_tree(tmp_path)
    manifest, contract, receipts = _manifest_for_cases(PROVIDER_CASES[3])
    result = _attach(root, manifest, "prometheus-matrix", contract, receipts)
    forged = deepcopy(result.bundle)
    record = forged["records"][0]
    if mutation == "p120_source_id":
        record["p120_record"]["source_id"] = "forged-source"
    else:
        record[mutation] = {
            "source_record_hash": stable_hash({"forged": "source-record"}),
            "evidence_id": stable_hash({"forged": "evidence-id"}),
            "content_hash": stable_hash({"forged": "content"}),
            "provider": "loki",
            "format": "prometheus.query_range.forged.v1",
            "execution_receipt_ref": "not-a-sha256",
        }[mutation]
    record["record_hash"] = stable_hash({key: value for key, value in record.items() if key != "record_hash"})
    forged["bundle_hash"] = stable_hash({key: value for key, value in forged.items() if key != "bundle_hash"})

    with pytest.raises(P135ExportError, match=reason):
        validate_normalized_bundle(forged)


@pytest.mark.parametrize(
    ("raw_ref_field", "reason"),
    [
        ("source_hash", "p120_raw_ref_source_hash_mismatch"),
        ("record_id", "p120_raw_ref_record_id_mismatch"),
    ],
)
def test_rehashed_inner_p120_raw_provenance_tamper_is_rejected(
    tmp_path: Path,
    raw_ref_field: str,
    reason: str,
) -> None:
    root = _copy_fixture_tree(tmp_path)
    manifest, contract, receipts = _manifest_for_cases(PROVIDER_CASES[3])
    result = _attach(root, manifest, "prometheus-matrix", contract, receipts)
    forged = deepcopy(result.bundle)
    record = forged["records"][0]
    record["p120_record"]["raw_ref"][raw_ref_field] = (
        stable_hash({"forged": "inner-source"}) if raw_ref_field == "source_hash" else "forged-record-id"
    )
    source_record_hash = stable_hash(record["p120_record"]["raw_ref"])
    record["source_record_hash"] = source_record_hash
    record["evidence_id"] = stable_hash(
        {"source": forged["source_id"], "ordinal": record["ordinal"], "source_hash": source_record_hash}
    )
    record["content_hash"] = stable_hash(
        {"artifact": forged["artifact_content_hash"], "record": source_record_hash}
    )
    record["record_hash"] = stable_hash({key: value for key, value in record.items() if key != "record_hash"})
    forged["bundle_hash"] = stable_hash({key: value for key, value in forged.items() if key != "bundle_hash"})

    with pytest.raises(P135ExportError, match=reason):
        validate_normalized_bundle(forged)


def test_otlp_provenance_is_not_labeled_as_prometheus(tmp_path: Path) -> None:
    root = _copy_fixture_tree(tmp_path)
    manifest, contract, receipts = _manifest_for_cases(PROVIDER_CASES[2])

    result = _attach(root, manifest, "otlp-metrics", contract, receipts)

    assert {record["p120_record"]["source_schema"] for record in result.bundle["records"]} == {"opentelemetry"}


def test_zero_counter_helpers_reject_nonzero_forbidden_authority_and_boolean_activity() -> None:
    authority = zero_forbidden_authority()
    assert all(type(value) is int and value == 0 for value in authority.values())
    activity = zero_observation_activity()
    assert all(type(value) is int and value == 0 for value in activity.values())

    authority["network_call_count"] = 1
    with pytest.raises(P135ExportError, match="network_call_count_nonzero"):
        validate_execution_ledger(
            {
                "schema_version": "p135.export_execution_ledger.v1",
                "manifest_hash": "sha256:" + "0" * 64,
                "contract_hash": "sha256:" + "0" * 64,
                "receipts": [],
                "counters": activity,
                "authority_counters": authority,
                "ledger_hash": "sha256:" + "0" * 64,
            },
            {"manifest_hash": "sha256:" + "0" * 64},
            _contract(),
            [],
        )
