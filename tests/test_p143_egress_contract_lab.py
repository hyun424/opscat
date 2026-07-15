from __future__ import annotations

import hashlib
import http.client
import importlib
import os
import shutil
import socket
import ssl
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import app.services.p143_egress_contract_lab as p143
from app.api import approvals as approval_api
from app.api import incidents as incident_api
from app.connectors import prometheus as prometheus_connector
from app.connectors import sentry as sentry_connector
from app.services import audited_staging_transport_gate, controlled_remediation, p133_deadman_outbox, slack_ticket_draft_automation
from app.services.action_service import ActionService
from app.services.p110_evaluation import stable_hash
from app.services.p143_egress_contract_lab import (
    EgressContractError,
    build_egress_intent,
    evaluate_shadow_capability,
    list_egress_results,
    load_egress_contract_config,
    process_egress_contracts,
    project_shadow_provider,
    validate_egress_contract_config,
)
from tests.fixtures.p141.builders import write_json
from tests.fixtures.p143.builders import build_p143_fixture, read_json

ROOT = Path(__file__).resolve().parents[1]


def _first_source(fixture: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt = read_json(next(iter(sorted(fixture.p142.config.receipt_dir.glob("*.json")))))
    envelope = next(
        read_json(path)
        for path in sorted(fixture.p142.p141.config.envelope_dir.glob("*.json"))
        if read_json(path)["envelope_hash"] == receipt["p141_binding"]["envelope_hash"]
    )
    return envelope, receipt


def _profile(fixture: Any) -> dict[str, Any]:
    return read_json(fixture.profile_path)


def _rehash(value: dict[str, Any], field: str) -> None:
    value[field] = stable_hash({key: item for key, item in value.items() if key != field})


def _prepared_entry(journal: dict[str, Any], phase: str) -> dict[str, Any]:
    return next(entry for entry in journal["entries"] if entry["phase"] == phase)


def _rehash_prepared(entry: dict[str, Any], kind: str, hash_field: str) -> None:
    artifact = entry["data"][kind]
    _rehash(artifact, hash_field)
    entry["data"]["byte_sha256"] = "sha256:" + hashlib.sha256(p143.canonical_json(artifact) + b"\n").hexdigest()


def _write_canonical(path: Path, value: dict[str, Any]) -> None:
    path.write_bytes(p143.canonical_json(value) + b"\n")


def _replace_bound_artifact(directory: Path, old_id: str, new_id: str, value: dict[str, Any]) -> None:
    old_path = directory / f"{old_id[7:]}.json"
    new_path = directory / f"{new_id[7:]}.json"
    _write_canonical(new_path, value)
    if old_path != new_path:
        old_path.unlink()


def _coordinated_p143_title_forgery(fixture: Any) -> None:
    profile = _profile(fixture)
    envelopes = {
        read_json(path)["envelope_hash"]: read_json(path)
        for path in sorted(fixture.p142.p141.config.envelope_dir.glob("*.json"))
    }
    source_timestamps = {
        stable_hash({"receipt_hash": receipt["receipt_hash"]}): p143._canonical_timestamp(
            envelopes[receipt["p141_binding"]["envelope_hash"]]["source_event"]["occurred_at"]
        )
        for path in sorted(fixture.p142.config.receipt_dir.glob("*.json"))
        for receipt in [read_json(path)]
    }
    journals: list[tuple[Path, dict[str, Any]]] = []
    batch_bindings: list[dict[str, Any]] = []
    for journal_path in sorted(fixture.config.journal_dir.glob("*.json")):
        journal = read_json(journal_path)
        intent_entry = _prepared_entry(journal, "intent_prepared")
        intent = intent_entry["data"]["intent"]
        old_intent_id = intent["intent_id"]
        intent["title"] = "coordinated-forged-title"
        _rehash(intent, "intent_hash")
        _rehash_prepared(intent_entry, "intent", "intent_hash")
        _prepared_entry(journal, "intent_written")["data"] = {"intent_hash": intent["intent_hash"]}
        _replace_bound_artifact(fixture.config.intent_dir, old_intent_id, intent["intent_id"], intent)

        projection_hashes: list[str] = []
        result_hashes: list[str] = []
        projection_entries = [entry for entry in journal["entries"] if entry["phase"] == "projection_prepared"]
        projection_written = [entry for entry in journal["entries"] if entry["phase"] == "projection_written"]
        result_entries = [entry for entry in journal["entries"] if entry["phase"] == "capability_result_prepared"]
        result_written = [entry for entry in journal["entries"] if entry["phase"] == "capability_result_written"]
        for index, old_projection_entry in enumerate(projection_entries):
            old_projection = old_projection_entry["data"]["projection"]
            channel = next(item for item in profile["channels"] if item["channel_type"] == old_projection["channel_type"])
            projection = project_shadow_provider(intent, channel)
            result = evaluate_shadow_capability(projection, channel)
            old_result = result_entries[index]["data"]["result"]
            _replace_bound_artifact(
                fixture.config.projection_dir,
                old_projection["projection_id"],
                projection["projection_id"],
                projection,
            )
            _replace_bound_artifact(fixture.config.result_dir, old_result["result_id"], result["result_id"], result)
            old_projection_entry["data"] = {
                "projection": projection,
                "byte_sha256": "sha256:" + hashlib.sha256(p143.canonical_json(projection) + b"\n").hexdigest(),
            }
            projection_written[index]["data"] = {"projection_hash": projection["projection_hash"]}
            result_entries[index]["data"] = {
                "result": result,
                "byte_sha256": "sha256:" + hashlib.sha256(p143.canonical_json(result) + b"\n").hexdigest(),
            }
            result_written[index]["data"] = {"result_hash": result["result_hash"]}
            projection_hashes.append(projection["projection_hash"])
            result_hashes.append(result["result_hash"])
        batch_bindings.append(
            {
                "source_id": journal["source_id"],
                "source_occurred_at": source_timestamps[journal["source_id"]],
                "intent_hash": intent["intent_hash"],
                "projection_hashes": projection_hashes,
                "result_hashes": result_hashes,
            }
        )
        journals.append((journal_path, journal))

    source_order = [
        stable_hash({"receipt_hash": read_json(path)["receipt_hash"]})
        for path in sorted(fixture.p142.config.receipt_dir.glob("*.json"))
    ]
    batch_bindings.sort(key=lambda binding: source_order.index(binding["source_id"]))
    run = _prepared_entry(journals[0][1], "run_prepared")["data"]["run"]
    old_run_hash = run["run_hash"]
    run["profile_hash"] = stable_hash(profile)
    run["source_batch_hash"] = stable_hash({"source_artifacts": batch_bindings})
    _rehash(run, "run_hash")
    _replace_bound_artifact(fixture.config.run_dir, old_run_hash, run["run_hash"], run)
    for journal_path, journal in journals:
        run_prepared = _prepared_entry(journal, "run_prepared")
        run_prepared["data"] = {
            "run": run,
            "byte_sha256": "sha256:" + hashlib.sha256(p143.canonical_json(run) + b"\n").hexdigest(),
        }
        _prepared_entry(journal, "run_written")["data"] = {"run_hash": run["run_hash"]}
        _rehash(journal, "journal_hash")
        write_json(journal_path, journal)


def _coordinated_run_timestamp_forgery(fixture: Any) -> None:
    journals = [
        (path, read_json(path))
        for path in sorted(fixture.config.journal_dir.glob("*.json"))
    ]
    run = dict(_prepared_entry(journals[0][1], "run_prepared")["data"]["run"])
    old_run_hash = run["run_hash"]
    run["generated_at"] = "2099-12-31T23:59:59Z"
    _rehash(run, "run_hash")
    _replace_bound_artifact(fixture.config.run_dir, old_run_hash, run["run_hash"], run)
    for journal_path, journal in journals:
        _prepared_entry(journal, "run_prepared")["data"] = {
            "run": run,
            "byte_sha256": "sha256:" + hashlib.sha256(p143.canonical_json(run) + b"\n").hexdigest(),
        }
        _prepared_entry(journal, "run_written")["data"] = {"run_hash": run["run_hash"]}
        _rehash(journal, "journal_hash")
        write_json(journal_path, journal)


def _use_copied_frozen_dependencies(fixture: Any) -> Path:
    eval_root = fixture.root / "frozen" / "evals"
    shutil.copytree(ROOT / "evals/p142", eval_root / "p142")
    shutil.copytree(ROOT / "evals/p141", eval_root / "p141")
    (eval_root / "p133").mkdir(parents=True)
    shutil.copy2(ROOT / "evals/p133/release-evidence.json", eval_root / "p133/release-evidence.json")
    raw = read_json(fixture.config_path)
    raw["p142_release_evidence_path"] = str(eval_root / "p142/output/release-evidence.json")
    raw["immutable_read_roots"] = [*raw["immutable_read_roots"], str(eval_root)]
    write_json(fixture.config_path, raw)
    fixture.config = load_egress_contract_config(fixture.config_path)
    return eval_root


def test_config_accepts_exact_closed_schema(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    assert fixture.config.schema_version == "p143.egress_contract_config.v1"
    assert validate_egress_contract_config(fixture.config)["status"] == "valid"


def test_config_rejects_unknown_fields(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    raw = read_json(fixture.config_path)
    raw["unknown"] = "x"
    write_json(fixture.config_path, raw)
    with pytest.raises(EgressContractError, match="invalid_configuration_fields"):
        load_egress_contract_config(fixture.config_path)


def test_config_rejects_p143_authority_words(tmp_path: Path) -> None:
    for index, key in enumerate(("send", "deliver")):
        fixture = build_p143_fixture(tmp_path / str(index))
        raw = read_json(fixture.config_path)
        raw[key] = "forbidden"
        write_json(fixture.config_path, raw)
        with pytest.raises(EgressContractError, match="forbidden_configuration_field"):
            load_egress_contract_config(fixture.config_path)


def test_config_rejects_endpoint_url_and_webhook_fields(tmp_path: Path) -> None:
    for index, key in enumerate(("endpoint", "url", "webhook")):
        fixture = build_p143_fixture(tmp_path / str(index))
        raw = read_json(fixture.config_path)
        raw[key] = "forbidden"
        write_json(fixture.config_path, raw)
        with pytest.raises(EgressContractError, match="forbidden_configuration_field"):
            load_egress_contract_config(fixture.config_path)


def test_config_rejects_auth_token_header_and_secret_fields(tmp_path: Path) -> None:
    for index, key in enumerate(("auth", "token", "header", "secret")):
        fixture = build_p143_fixture(tmp_path / str(index))
        raw = read_json(fixture.config_path)
        raw[key] = "forbidden"
        write_json(fixture.config_path, raw)
        with pytest.raises(EgressContractError, match="forbidden_configuration_field"):
            load_egress_contract_config(fixture.config_path)


def test_config_rejects_dns_proxy_tls_and_provider_sdk_fields(tmp_path: Path) -> None:
    for index, key in enumerate(("dns", "proxy", "tls", "provider_sdk")):
        fixture = build_p143_fixture(tmp_path / str(index))
        raw = read_json(fixture.config_path)
        raw[key] = "forbidden"
        write_json(fixture.config_path, raw)
        with pytest.raises(EgressContractError, match="forbidden_configuration_field"):
            load_egress_contract_config(fixture.config_path)


def test_paths_reject_traversal_symlink_and_hardlink(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    raw = read_json(fixture.config_path)
    raw["cursor_path"] = "../cursor.json"
    write_json(fixture.config_path, raw)
    with pytest.raises(EgressContractError, match="invalid_local_path"):
        load_egress_contract_config(fixture.config_path)
    link_case = build_p143_fixture(tmp_path / "link")
    os.link(link_case.config_path, link_case.config_path.with_name("copy.json"))
    with pytest.raises(EgressContractError, match="configuration_has_multiple_links"):
        load_egress_contract_config(link_case.config_path)
    symlink_case = build_p143_fixture(tmp_path / "symlink")
    symlink_case.config.intent_dir.rmdir()
    symlink_case.config.intent_dir.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(EgressContractError, match="symlink"):
        process_egress_contracts(symlink_case.config)


def test_roots_reject_wrong_owner_and_writable_permissions(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    fixture.config.intent_dir.chmod(0o777)
    with pytest.raises(EgressContractError, match="unsafe_directory_permissions"):
        process_egress_contracts(fixture.config)


def test_roots_reject_read_write_overlap(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    raw = read_json(fixture.config_path)
    raw["intent_dir"] = str(fixture.p142.p142_data / "intents")
    write_json(fixture.config_path, raw)
    with pytest.raises(EgressContractError, match="read_write_root_overlap"):
        load_egress_contract_config(fixture.config_path)


def test_budgets_reject_boolean_negative_and_overflow(tmp_path: Path) -> None:
    for index, value in enumerate((True, -1, 10_000_001)):
        fixture = build_p143_fixture(tmp_path / str(index))
        raw = read_json(fixture.config_path)
        raw["max_sources_per_run"] = value
        write_json(fixture.config_path, raw)
        with pytest.raises(EgressContractError, match="invalid_integer_budget"):
            load_egress_contract_config(fixture.config_path)


def test_p142_exact_qualified_release_required(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    raw = read_json(fixture.config_path)
    raw["p142_release_evidence_path"] = str(fixture.p142.p141_release_evidence_path)
    write_json(fixture.config_path, raw)
    with pytest.raises(EgressContractError, match="p142_release_dependency_drift"):
        validate_egress_contract_config(load_egress_contract_config(fixture.config_path))


def test_p142_stale_release_evidence_rejected(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    evidence = read_json(fixture.config.p142_release_evidence_path)
    copied = tmp_path / "stale-p142-release.json"
    evidence["status"] = "stale"
    evidence["evidence_hash"] = stable_hash({key: value for key, value in evidence.items() if key != "evidence_hash"})
    write_json(copied, evidence)
    raw = read_json(fixture.config_path)
    raw["p142_release_evidence_path"] = str(copied)
    write_json(fixture.config_path, raw)
    with pytest.raises(EgressContractError, match="p142_release_dependency_drift"):
        validate_egress_contract_config(load_egress_contract_config(fixture.config_path))


def test_p142_receipt_schema_drift_rejected(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    receipt_path = next(fixture.p142.config.receipt_dir.glob("*.json"))
    receipt = read_json(receipt_path)
    receipt["extra"] = "drift"
    write_json(receipt_path, receipt)
    with pytest.raises(EgressContractError, match="receipt"):
        process_egress_contracts(fixture.config)


def test_p142_receipt_hash_drift_rejected(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    receipt_path = next(fixture.p142.config.receipt_dir.glob("*.json"))
    receipt = read_json(receipt_path)
    receipt["failure_class"] = "tampered"
    write_json(receipt_path, receipt)
    with pytest.raises(EgressContractError, match="receipt_hash_invalid"):
        process_egress_contracts(fixture.config)


def test_p142_production_delivered_true_rejected(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    receipt_path = next(fixture.p142.config.receipt_dir.glob("*.json"))
    receipt = read_json(receipt_path)
    receipt["production_delivered"] = True
    receipt["receipt_hash"] = stable_hash({key: value for key, value in receipt.items() if key != "receipt_hash"})
    write_json(receipt_path, receipt)
    with pytest.raises(EgressContractError, match="receipt_authority_invalid"):
        process_egress_contracts(fixture.config)


def test_p141_envelope_binding_required(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    for path in fixture.p142.p141.config.envelope_dir.glob("*.json"):
        path.unlink()
    with pytest.raises(EgressContractError, match="envelope_missing"):
        process_egress_contracts(fixture.config)


def test_p141_envelope_hash_drift_rejected(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    envelope_path = next(fixture.p142.p141.config.envelope_dir.glob("*.json"))
    envelope = read_json(envelope_path)
    envelope["message"]["title"] = "tampered"
    write_json(envelope_path, envelope)
    with pytest.raises(EgressContractError, match="p141_envelope_hash_invalid"):
        process_egress_contracts(fixture.config)


@pytest.mark.parametrize(
    "mutation",
    (
        "dispatch_destination",
        "attempt_identity",
        "journal_phase",
        "request_hash",
        "response_hash",
        "p141_event",
        "p142_config",
        "freeze",
        "matrix",
        "final_review",
        "profile",
        "p141_release",
        "p133_release",
    ),
)
def test_p133_p141_p142_dependency_graph_is_immutable(tmp_path: Path, mutation: str) -> None:
    fixture = build_p143_fixture(tmp_path)
    dispatch_path = next(fixture.p142.config.dispatch_dir.glob("*.json"))
    journal_path = next(fixture.p142.config.journal_dir.glob("*.json"))
    receipt_path = next(fixture.p142.config.receipt_dir.glob("*.json"))
    dispatch = read_json(dispatch_path)
    journal = read_json(journal_path)
    receipt = read_json(receipt_path)
    if mutation == "dispatch_destination":
        dispatch["destination_id"] = "other"
        _rehash(dispatch, "dispatch_hash")
        write_json(dispatch_path, dispatch)
    elif mutation == "attempt_identity":
        journal["entries"][0]["attempt_id"] = "sha256:" + "1" * 64
        _rehash(journal, "journal_hash")
        write_json(journal_path, journal)
    elif mutation == "journal_phase":
        journal["entries"][0]["phases"].append("request_committed")
        _rehash(journal, "journal_hash")
        write_json(journal_path, journal)
    elif mutation == "request_hash":
        dispatch["request_body_hash"] = "sha256:" + "2" * 64
        _rehash(dispatch, "dispatch_hash")
        write_json(dispatch_path, dispatch)
    elif mutation == "response_hash":
        receipt["response_body_hash"] = "sha256:" + "3" * 64
        _rehash(receipt, "receipt_hash")
        terminal = journal["entries"][-1]
        terminal["receipt_intent"]["receipt"] = receipt
        terminal["receipt_intent"]["receipt_bytes_sha256"] = "sha256:" + hashlib.sha256(
            p143.canonical_json(receipt) + b"\n"
        ).hexdigest()
        terminal["receipt_hash"] = receipt["receipt_hash"]
        _rehash(journal, "journal_hash")
        write_json(receipt_path, receipt)
        write_json(journal_path, journal)
    elif mutation == "p141_event":
        event_path = next(fixture.p142.p141.config.p133_config.outbox_dir.glob("*.json"))
        event = read_json(event_path)
        event["transition_kind"] = "recovered"
        write_json(event_path, event)
    elif mutation == "p142_config":
        config = read_json(fixture.p142.config_path)
        config["max_attempts"] += 1
        write_json(fixture.p142.config_path, config)
    else:
        eval_root = _use_copied_frozen_dependencies(fixture)
        paths = {
            "freeze": eval_root / "p142/output/freeze-manifest.json",
            "matrix": eval_root / "p142/output/canonical-matrix.json",
            "final_review": eval_root / "p142/final-implementation-review.json",
            "profile": eval_root / "p142/input/loopback-transport-lab-profile.json",
            "p141_release": eval_root / "p141/output/release-evidence.json",
            "p133_release": eval_root / "p133/release-evidence.json",
        }
        artifact = read_json(paths[mutation])
        artifact["tampered"] = True
        hash_field = {
            "freeze": "freeze_manifest_hash",
            "matrix": "matrix_hash",
            "final_review": "review_hash",
            "p141_release": "evidence_hash",
            "p133_release": "release_evidence_hash",
        }.get(mutation)
        if hash_field:
            _rehash(artifact, hash_field)
        write_json(paths[mutation], artifact)
    with pytest.raises(EgressContractError, match="dependency_graph_invalid"):
        process_egress_contracts(fixture.config)


@pytest.mark.parametrize("transition", ["opened", "updated", "reminder", "recovered"])
def test_opened_transition_intent_built(tmp_path: Path, transition: str) -> None:
    fixture = build_p143_fixture(tmp_path)
    envelope, receipt = _first_source(fixture)
    envelope["source_event"]["transition_kind"] = transition
    envelope["envelope_hash"] = stable_hash({key: value for key, value in envelope.items() if key != "envelope_hash"})
    intent = build_egress_intent(fixture.config, envelope, receipt)
    assert intent["transition_kind"] == transition
    assert intent["severity"] in {"critical", "warning", "info", "recovered"}


def test_updated_transition_intent_built(tmp_path: Path) -> None:
    test_opened_transition_intent_built(tmp_path, "updated")


def test_reminder_transition_intent_built(tmp_path: Path) -> None:
    test_opened_transition_intent_built(tmp_path, "reminder")


def test_recovered_transition_intent_built(tmp_path: Path) -> None:
    test_opened_transition_intent_built(tmp_path, "recovered")


def test_intent_id_is_deterministic(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    envelope, receipt = _first_source(fixture)
    assert build_egress_intent(fixture.config, envelope, receipt)["intent_id"] == build_egress_intent(fixture.config, envelope, receipt)["intent_id"]


def test_idempotency_key_is_deterministic(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    envelope, receipt = _first_source(fixture)
    assert build_egress_intent(fixture.config, envelope, receipt)["idempotency_key"].startswith("sha256:")


def test_dedupe_key_is_deterministic(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    envelope, receipt = _first_source(fixture)
    assert build_egress_intent(fixture.config, envelope, receipt)["dedupe_key"] == build_egress_intent(fixture.config, envelope, receipt)["dedupe_key"]


def test_severity_mapping_is_closed(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    envelope, receipt = _first_source(fixture)
    assert build_egress_intent(fixture.config, envelope, receipt)["severity"] == "critical"


def test_unsupported_severity_fails_closed(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    envelope, receipt = _first_source(fixture)
    envelope["source_event"]["transition_kind"] = "unknown"
    envelope["envelope_hash"] = stable_hash({key: value for key, value in envelope.items() if key != "envelope_hash"})
    with pytest.raises(EgressContractError, match="unsupported_transition_kind"):
        build_egress_intent(fixture.config, envelope, receipt)


def test_truncation_is_deterministic_and_recorded(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    envelope, receipt = _first_source(fixture)
    envelope["message"]["summary"] = "x" * 1000
    envelope["envelope_hash"] = stable_hash({key: value for key, value in envelope.items() if key != "envelope_hash"})
    projection = project_shadow_provider(build_egress_intent(fixture.config, envelope, receipt), _profile(fixture)["channels"][0])
    assert projection["truncation"]["body_truncated"] is True
    assert projection == project_shadow_provider(build_egress_intent(fixture.config, envelope, receipt), _profile(fixture)["channels"][0])


def test_evidence_refs_preserved_without_raw_secrets(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    envelope, receipt = _first_source(fixture)
    intent = build_egress_intent(fixture.config, envelope, receipt)
    assert intent["evidence_refs"]
    assert "secret" not in p143.canonical_json(intent).decode("utf-8").lower()


def test_provider_neutral_projection_is_byte_stable(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    envelope, receipt = _first_source(fixture)
    profile = _profile(fixture)["channels"][0]
    projection = project_shadow_provider(build_egress_intent(fixture.config, envelope, receipt), profile)
    assert p143.canonical_json(projection) == p143.canonical_json(project_shadow_provider(build_egress_intent(fixture.config, envelope, receipt), profile))


@pytest.mark.parametrize("channel_type", ["chat_message", "email_message", "pager_event", "incident_comment"])
def test_chat_shadow_profile_compatibility_pass(tmp_path: Path, channel_type: str) -> None:
    fixture = build_p143_fixture(tmp_path)
    envelope, receipt = _first_source(fixture)
    channel = next(item for item in _profile(fixture)["channels"] if item["channel_type"] == channel_type)
    result = evaluate_shadow_capability(project_shadow_provider(build_egress_intent(fixture.config, envelope, receipt), channel), channel)
    assert result["compatible"] is True


def test_email_shadow_profile_compatibility_pass(tmp_path: Path) -> None:
    test_chat_shadow_profile_compatibility_pass(tmp_path, "email_message")


def test_pager_shadow_profile_compatibility_pass(tmp_path: Path) -> None:
    test_chat_shadow_profile_compatibility_pass(tmp_path, "pager_event")


def test_incident_comment_shadow_profile_compatibility_pass(tmp_path: Path) -> None:
    test_chat_shadow_profile_compatibility_pass(tmp_path, "incident_comment")


def test_unsupported_channel_fails_closed(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    envelope, receipt = _first_source(fixture)
    channel = dict(_profile(fixture)["channels"][0], channel_type="sms")
    with pytest.raises(EgressContractError, match="unsupported_channel_type"):
        project_shadow_provider(build_egress_intent(fixture.config, envelope, receipt), channel)


def test_missing_required_capability_fails_closed(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    envelope, receipt = _first_source(fixture)
    channel = dict(_profile(fixture)["channels"][0], supports_dedupe=False)
    result = evaluate_shadow_capability(project_shadow_provider(build_egress_intent(fixture.config, envelope, receipt), channel), channel)
    assert result["compatible"] is False
    assert "dedupe_not_supported" in result["reasons"]


def test_payload_size_limit_fails_closed(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    envelope, receipt = _first_source(fixture)
    channel = dict(_profile(fixture)["channels"][0], max_body_chars=4)
    result = evaluate_shadow_capability(project_shadow_provider(build_egress_intent(fixture.config, envelope, receipt), channel), channel)
    assert result["compatible"] is False


def test_evidence_reference_limit_fails_closed(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    envelope, receipt = _first_source(fixture)
    envelope["message"]["evidence_refs"] = [{"kind": "hash", "value": f"sha256:{index:064x}"} for index in range(20)]
    envelope["envelope_hash"] = stable_hash({key: value for key, value in envelope.items() if key != "envelope_hash"})
    channel = dict(_profile(fixture)["channels"][0], max_evidence_refs=2)
    result = evaluate_shadow_capability(project_shadow_provider(build_egress_intent(fixture.config, envelope, receipt), channel), channel)
    assert result["compatible"] is False
    assert "evidence_ref_limit_exceeded" in result["reasons"]


def test_retry_classification_is_local_evidence_only(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    process_egress_contracts(fixture.config)
    assert {item["retry_classification"] for item in list_egress_results(fixture.config)} == {"local_no_retry"}


def test_rate_limit_semantics_are_manifest_only(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    envelope, receipt = _first_source(fixture)
    projection = project_shadow_provider(build_egress_intent(fixture.config, envelope, receipt), _profile(fixture)["channels"][0])
    assert projection["rate_limit"] == {"policy": "manifest_only", "wait_performed": False}


def test_valid_processing_opens_no_socket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = build_p143_fixture(tmp_path)
    monkeypatch.setattr(socket, "socket", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("socket")))
    run = process_egress_contracts(fixture.config)
    assert run["forbidden_counters"] == p143.zero_forbidden_counters()


def test_forbidden_network_environment_provider_entrypoints_stay_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = build_p143_fixture(tmp_path)

    def blocked(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("forbidden P143 authority entrypoint")

    for target, name in (
        (socket, "socket"),
        (socket, "create_connection"),
        (socket, "getaddrinfo"),
        (os, "getenv"),
        (os, "system"),
        (os, "popen"),
        (subprocess, "run"),
        (subprocess, "Popen"),
        (subprocess, "call"),
        (subprocess, "check_call"),
        (subprocess, "check_output"),
        (http.client, "HTTPConnection"),
        (http.client, "HTTPSConnection"),
        (urllib.request, "urlopen"),
        (ssl, "create_default_context"),
        (ssl.SSLContext, "wrap_socket"),
        (importlib, "import_module"),
        (sentry_connector, "urlopen"),
        (prometheus_connector, "urlopen"),
        (p133_deadman_outbox, "acknowledge_event"),
        (approval_api, "propose_action"),
        (approval_api, "approve_action"),
        (approval_api, "execute_action"),
        (incident_api, "approve_incident_action_alias"),
        (controlled_remediation, "run_controlled_remediation_fixture"),
        (slack_ticket_draft_automation, "evaluate_slack_ticket_draft_fixture"),
        (audited_staging_transport_gate, "run_audited_staging_transport_gate_fixture"),
        (audited_staging_transport_gate.MockAuditedStagingTransport, "get"),
        (ActionService, "propose"),
        (ActionService, "approve"),
        (ActionService, "execute"),
    ):
        monkeypatch.setattr(target, name, blocked)
    monkeypatch.setattr(type(os.environ), "get", blocked)
    monkeypatch.setattr(type(os.environ), "__getitem__", blocked)
    run = process_egress_contracts(fixture.config)
    assert all(value == 0 for value in run["forbidden_counters"].values())


def test_no_subprocess_or_shell_path_exists() -> None:
    source = Path(p143.__file__).read_text(encoding="utf-8")
    assert "import subprocess" not in source
    assert "os.system" not in source


def test_completed_replay_opens_no_io_and_is_byte_identical(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = build_p143_fixture(tmp_path)
    first = process_egress_contracts(fixture.config)
    before = {path.relative_to(fixture.config.intent_dir.parent).as_posix(): path.read_bytes() for path in fixture.config.intent_dir.parent.rglob("*.json")}
    monkeypatch.setattr(socket, "socket", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("socket")))
    monkeypatch.setattr(socket, "create_connection", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("socket")))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("dns")))
    second = process_egress_contracts(fixture.config)
    after = {path.relative_to(fixture.config.intent_dir.parent).as_posix(): path.read_bytes() for path in fixture.config.intent_dir.parent.rglob("*.json")}
    assert first["run_hash"] == second["run_hash"]
    assert before == after


def test_completed_replay_rejects_coordinated_self_consistent_artifact_chain_forgery(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    process_egress_contracts(fixture.config)
    cursor_before = fixture.config.cursor_path.read_bytes()
    _coordinated_p143_title_forgery(fixture)
    with pytest.raises(EgressContractError, match="expected|source|profile|artifact|binding"):
        process_egress_contracts(fixture.config)
    assert fixture.config.cursor_path.read_bytes() == cursor_before


def test_completed_replay_rejects_coordinated_run_generated_at_forgery(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    run = process_egress_contracts(
        fixture.config,
        wall_clock=lambda: datetime(2088, 1, 1, tzinfo=UTC),
    )
    source_timestamps = [
        read_json(path)["source_event"]["occurred_at"]
        for path in sorted(fixture.p142.p141.config.envelope_dir.glob("*.json"))
    ]
    expected = max(
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        for timestamp in source_timestamps
    )
    assert run["generated_at"] == expected.isoformat(timespec="microseconds").replace("+00:00", "Z")
    cursor_before = fixture.config.cursor_path.read_bytes()
    _coordinated_run_timestamp_forgery(fixture)
    with pytest.raises(EgressContractError, match="expected_run_binding_invalid"):
        process_egress_contracts(fixture.config)
    assert fixture.config.cursor_path.read_bytes() == cursor_before


def test_run_generated_at_uses_chronological_utc_max_with_mixed_fractional_precision(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    source_bindings = [
        {
            "source_id": "sha256:" + str(index) * 64,
            "source_occurred_at": timestamp,
            "intent_hash": "sha256:" + str(index) * 64,
            "projection_hashes": [],
            "result_hashes": [],
        }
        for index, timestamp in enumerate(
            ("2026-07-14T00:00:00Z", "2026-07-14T00:00:00.100000Z"),
            start=1,
        )
    ]
    run = p143._build_run(
        fixture.config,
        profile_hash=stable_hash(_profile(fixture)),
        source_bindings=source_bindings,
        counters=p143.zero_allowed_counters(),
    )
    assert run["generated_at"] == "2026-07-14T00:00:00.100000Z"


@pytest.mark.parametrize(
    "timestamp",
    (
        "2026-07-14T00:00:00",
        "2026-07-14T09:00:00+09:00",
        "not-a-timestamp",
    ),
)
def test_run_generated_at_rejects_invalid_or_non_utc_source_timestamps(tmp_path: Path, timestamp: str) -> None:
    fixture = build_p143_fixture(tmp_path)
    source_binding = {
        "source_id": "sha256:" + "1" * 64,
        "source_occurred_at": timestamp,
        "intent_hash": "sha256:" + "2" * 64,
        "projection_hashes": [],
        "result_hashes": [],
    }
    with pytest.raises(EgressContractError, match="invalid_source_timestamp"):
        p143._build_run(
            fixture.config,
            profile_hash=stable_hash(_profile(fixture)),
            source_bindings=[source_binding],
            counters=p143.zero_allowed_counters(),
        )


def test_completed_replay_rejects_exact_shadow_profile_drift_even_when_projection_is_unchanged(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    process_egress_contracts(fixture.config)
    profile = _profile(fixture)
    profile["channels"][0]["max_title_chars"] += 1
    write_json(fixture.profile_path, profile)
    with pytest.raises(EgressContractError, match="profile|expected|binding"):
        process_egress_contracts(fixture.config)


def test_partial_recovery_rejects_exact_shadow_profile_drift_before_cursor_progress(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    with pytest.raises(RuntimeError, match="injected_crash"):
        process_egress_contracts(fixture.config, crash_after="intent_prepared")
    profile = _profile(fixture)
    profile["channels"][0]["max_title_chars"] += 1
    write_json(fixture.profile_path, profile)
    with pytest.raises(EgressContractError, match="profile|expected|binding"):
        process_egress_contracts(fixture.config)
    assert not fixture.config.cursor_path.exists()


def test_recovery_validates_current_source_graph_before_publishing_prepared_run(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    with pytest.raises(RuntimeError, match="injected_crash"):
        process_egress_contracts(fixture.config, crash_after="cursor_written")
    envelope_path = next(fixture.p142.p141.config.envelope_dir.glob("*.json"))
    envelope = read_json(envelope_path)
    envelope["message"]["title"] = "source-drift"
    _rehash(envelope, "envelope_hash")
    write_json(envelope_path, envelope)
    assert not list(fixture.config.run_dir.glob("*.json"))
    with pytest.raises(EgressContractError, match="dependency|envelope|source|binding"):
        process_egress_contracts(fixture.config)
    assert not list(fixture.config.run_dir.glob("*.json"))
    assert all(not any(entry["phase"] == "run_written" for entry in read_json(path)["entries"]) for path in fixture.config.journal_dir.glob("*.json"))


def test_intent_prepare_and_write_crashes_recover_byte_identically(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    with pytest.raises(RuntimeError, match="injected_crash"):
        process_egress_contracts(fixture.config, crash_after="intent_prepared")
    recovered = process_egress_contracts(fixture.config)
    assert recovered["processed_source_count"] > 0


def test_projection_prepare_and_write_crashes_recover_byte_identically(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    with pytest.raises(RuntimeError, match="injected_crash"):
        process_egress_contracts(fixture.config, crash_after="projection_prepared")
    recovered = process_egress_contracts(fixture.config)
    assert recovered["processed_source_count"] > 0


def test_result_cursor_and_run_crashes_recover_byte_identically(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    with pytest.raises(RuntimeError, match="injected_crash"):
        process_egress_contracts(fixture.config, crash_after="cursor_written")
    journals = [read_json(path) for path in fixture.config.journal_dir.glob("*.json")]
    prepared = [next(entry for entry in journal["entries"] if entry["phase"] == "run_prepared")["data"] for journal in journals]
    assert all(item == prepared[0] for item in prepared)
    prepared_run = prepared[0]["run"]
    assert prepared_run["run_hash"] == stable_hash({key: value for key, value in prepared_run.items() if key != "run_hash"})
    assert prepared[0]["byte_sha256"] == "sha256:" + hashlib.sha256(p143.canonical_json(prepared_run) + b"\n").hexdigest()
    recovered = process_egress_contracts(fixture.config)
    run_path = fixture.config.run_dir / f"{recovered['run_hash'][7:]}.json"
    assert recovered == prepared_run
    assert run_path.read_bytes() == p143.canonical_json(prepared_run) + b"\n"

    published = build_p143_fixture(tmp_path / "published")
    with pytest.raises(RuntimeError, match="injected_crash"):
        process_egress_contracts(published.config, crash_after="run_published")
    published_bytes = next(published.config.run_dir.glob("*.json")).read_bytes()
    assert p143.canonical_json(process_egress_contracts(published.config)) + b"\n" == published_bytes


@pytest.mark.parametrize("mutation", ("duplicate", "reorder", "missing_prepared", "conflicting_prepared"))
def test_replay_journal_phase_graph_fails_closed(tmp_path: Path, mutation: str) -> None:
    fixture = build_p143_fixture(tmp_path)
    with pytest.raises(RuntimeError, match="injected_crash"):
        process_egress_contracts(fixture.config, crash_after="cursor_written")
    path = next(fixture.config.journal_dir.glob("*.json"))
    journal = read_json(path)
    entries = journal["entries"]
    if mutation == "duplicate":
        entries.append(dict(entries[-1], ordinal=len(entries)))
    elif mutation == "reorder":
        entries[-2], entries[-1] = entries[-1], entries[-2]
        for ordinal, entry in enumerate(entries):
            entry["ordinal"] = ordinal
    elif mutation == "missing_prepared":
        entries[:] = [entry for entry in entries if entry["phase"] != "run_prepared"]
        for ordinal, entry in enumerate(entries):
            entry["ordinal"] = ordinal
    else:
        prepared = next(entry for entry in entries if entry["phase"] == "run_prepared")
        prepared["data"]["run"]["processed_source_count"] += 1
    _rehash(journal, "journal_hash")
    write_json(path, journal)
    with pytest.raises(EgressContractError, match="journal|prepared|replay"):
        process_egress_contracts(fixture.config)


@pytest.mark.parametrize(
    ("phase", "kind", "hash_field", "field"),
    (
        ("intent_prepared", "intent", "intent_hash", "title"),
        ("projection_prepared", "projection", "projection_hash", "channel_type"),
        ("capability_result_prepared", "result", "result_hash", "retry_classification"),
        ("run_prepared", "run", "run_hash", "generated_at"),
    ),
)
def test_prepared_artifacts_are_cross_bound_to_published_bytes(
    tmp_path: Path,
    phase: str,
    kind: str,
    hash_field: str,
    field: str,
) -> None:
    fixture = build_p143_fixture(tmp_path)
    process_egress_contracts(fixture.config)
    journal_path = next(fixture.config.journal_dir.glob("*.json"))
    journal = read_json(journal_path)
    prepared = _prepared_entry(journal, phase)
    prepared["data"][kind][field] = "self-consistent-forgery"
    _rehash_prepared(prepared, kind, hash_field)
    _rehash(journal, "journal_hash")
    write_json(journal_path, journal)
    with pytest.raises(EgressContractError, match="prepared|conflicting_replay_artifact|binding"):
        process_egress_contracts(fixture.config)


@pytest.mark.parametrize(
    "phase",
    ("intent_written", "projection_written", "capability_result_written", "cursor_written", "run_written"),
)
def test_written_phases_are_cross_bound_to_prepared_and_published_artifacts(tmp_path: Path, phase: str) -> None:
    fixture = build_p143_fixture(tmp_path)
    process_egress_contracts(fixture.config)
    journal_path = next(fixture.config.journal_dir.glob("*.json"))
    journal = read_json(journal_path)
    entry = _prepared_entry(journal, phase)
    key = next(iter(entry["data"]))
    entry["data"][key] = "sha256:" + "f" * 64
    _rehash(journal, "journal_hash")
    write_json(journal_path, journal)
    with pytest.raises(EgressContractError, match="journal|binding|conflicting_replay_artifact"):
        process_egress_contracts(fixture.config)


def test_cursor_stops_at_last_processed_source_when_budget_is_bounded(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path, max_sources_per_run=1)
    receipt = read_json(sorted(fixture.p142.config.receipt_dir.glob("*.json"))[0])
    expected_source_id = stable_hash({"receipt_hash": receipt["receipt_hash"]})
    process_egress_contracts(fixture.config)
    assert read_json(fixture.config.cursor_path)["last_source_id"] == expected_source_id


def test_bounded_processing_continues_after_completed_runs_until_all_sources_are_consumed(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path, max_sources_per_run=1)
    source_ids = [
        stable_hash({"receipt_hash": read_json(path)["receipt_hash"]})
        for path in sorted(fixture.p142.config.receipt_dir.glob("*.json"))
    ]
    assert len(source_ids) > 1
    runs = [process_egress_contracts(fixture.config) for _ in source_ids]
    assert [run["processed_source_count"] for run in runs] == [1] * len(source_ids)
    assert len({run["run_hash"] for run in runs}) == len(source_ids)
    assert read_json(fixture.config.cursor_path)["last_source_id"] == source_ids[-1]
    assert len(list(fixture.config.journal_dir.glob("*.json"))) == len(source_ids)
    assert process_egress_contracts(fixture.config)["run_hash"] == runs[-1]["run_hash"]


ATOMIC_CRASH_WINDOWS = tuple(
    f"{kind}:{stage}"
    for kind in ("intent", "projection", "result", "cursor", "run")
    for stage in ("file_fsync", "before_replace", "replace", "after_replace", "directory_fsync")
)


@pytest.mark.parametrize("crash_after", (*ATOMIC_CRASH_WINDOWS, "result:before_cursor", "cursor_written", "run_published"))
def test_all_approved_atomic_crash_windows_recover_or_fail_before_cursor(tmp_path: Path, crash_after: str) -> None:
    fixture = build_p143_fixture(tmp_path)
    with pytest.raises(RuntimeError, match="injected_crash"):
        process_egress_contracts(fixture.config, crash_after=crash_after)
    run = process_egress_contracts(fixture.config)
    assert run["forbidden_counters"] == p143.zero_forbidden_counters()
    assert read_json(fixture.config.cursor_path)["last_source_id"] is not None
    for journal_path in fixture.config.journal_dir.glob("*.json"):
        journal = read_json(journal_path)
        assert [entry["ordinal"] for entry in journal["entries"]] == list(range(len(journal["entries"])))
        for entry in journal["entries"]:
            binding = {
                "intent_prepared": ("intent", "intent_id", fixture.config.intent_dir),
                "projection_prepared": ("projection", "projection_id", fixture.config.projection_dir),
                "capability_result_prepared": ("result", "result_id", fixture.config.result_dir),
                "run_prepared": ("run", "run_hash", fixture.config.run_dir),
            }.get(entry["phase"])
            if binding is None:
                continue
            kind, id_field, directory = binding
            artifact = entry["data"][kind]
            assert (directory / f"{artifact[id_field][7:]}.json").read_bytes() == p143.canonical_json(artifact) + b"\n"


def test_bounded_later_batch_recovers_prepared_run_ahead_of_prior_cursor(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path, max_sources_per_run=1)
    first = process_egress_contracts(fixture.config)
    first_cursor = read_json(fixture.config.cursor_path)
    with pytest.raises(RuntimeError, match="injected_crash"):
        process_egress_contracts(fixture.config, crash_after="cursor:before_replace")
    assert read_json(fixture.config.cursor_path) == first_cursor
    second = process_egress_contracts(fixture.config)
    assert second["run_hash"] != first["run_hash"]
    assert read_json(fixture.config.cursor_path)["last_source_id"] != first_cursor["last_source_id"]
    assert second["allowed_counters"]["replay_journal_entry_count"] == sum(
        len(read_json(path)["entries"]) for path in fixture.config.journal_dir.glob("*.json")
    )


def test_run_allowed_counters_reconcile_exactly_to_durable_artifacts(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path, max_sources_per_run=1)
    latest = process_egress_contracts(fixture.config)
    latest = process_egress_contracts(fixture.config)
    journal_entry_count = sum(len(read_json(path)["entries"]) for path in fixture.config.journal_dir.glob("*.json"))
    result_values = [read_json(path) for path in fixture.config.result_dir.glob("*.json")]
    assert latest["allowed_counters"] == {
        "capability_manifest_write_count": len(result_values),
        "compatibility_failure_count": sum(not value["compatible"] for value in result_values),
        "intent_projection_count": len(list(fixture.config.projection_dir.glob("*.json"))),
        "replay_journal_entry_count": journal_entry_count,
        "schema_rejection_count": 0,
        "shadow_provider_validation_count": len(result_values),
    }
    assert p143.measured_allowed_counters() == latest["allowed_counters"]


def test_self_consistent_run_counter_forgery_fails_artifact_reconciliation(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    run = process_egress_contracts(fixture.config)
    old_run_path = fixture.config.run_dir / f"{run['run_hash'][7:]}.json"
    run["allowed_counters"]["replay_journal_entry_count"] += 1
    _rehash(run, "run_hash")
    new_run_path = fixture.config.run_dir / f"{run['run_hash'][7:]}.json"
    new_run_path.write_bytes(p143.canonical_json(run) + b"\n")
    old_run_path.unlink()
    for journal_path in fixture.config.journal_dir.glob("*.json"):
        journal = read_json(journal_path)
        prepared = _prepared_entry(journal, "run_prepared")
        prepared["data"]["run"] = run
        prepared["data"]["byte_sha256"] = "sha256:" + hashlib.sha256(p143.canonical_json(run) + b"\n").hexdigest()
        _prepared_entry(journal, "run_written")["data"] = {"run_hash": run["run_hash"]}
        _rehash(journal, "journal_hash")
        write_json(journal_path, journal)
    with pytest.raises(EgressContractError, match="expected_run_binding_invalid|allowed_counter_artifact_mismatch"):
        process_egress_contracts(fixture.config)


def test_conflicting_replay_artifact_fails_closed(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    process_egress_contracts(fixture.config)
    intent_path = next(fixture.config.intent_dir.glob("*.json"))
    intent = read_json(intent_path)
    intent["severity"] = "forged"
    write_json(intent_path, intent)
    with pytest.raises(EgressContractError, match="conflicting_replay_artifact"):
        process_egress_contracts(fixture.config)


def test_lease_conflict_fails_before_processing(tmp_path: Path) -> None:
    fixture = build_p143_fixture(tmp_path)
    with fixture.config.lease_path.open("w", encoding="utf-8") as handle:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(EgressContractError, match="lease_conflict"):
            process_egress_contracts(fixture.config)
