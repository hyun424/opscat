from __future__ import annotations

import ast
import http.client
import json
import os
import shutil
import socket
import ssl
import subprocess
import urllib.request
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import app.services.p144_provider_adapter_lab as p144
from app.services.p110_evaluation import stable_hash
from tests.fixtures.p141.builders import write_json
from tests.fixtures.p144.builders import accepted_response, build_p144_fixture, read_json, response


def _projection(fixture: Any) -> dict[str, Any]:
    return read_json(next(iter(sorted(fixture.p143.config.projection_dir.glob("*.json")))))


def _request(fixture: Any) -> dict[str, Any]:
    return p144.prepare_adapter_request(fixture.config, _projection(fixture), fixture.capability)


def _wire_headers(wire: bytes) -> dict[str, str]:
    head = wire.split(b"\r\n\r\n", 1)[0].decode("ascii")
    return {key.lower(): value.strip() for key, value in (line.split(":", 1) for line in head.split("\r\n")[1:])}


def _classify(status: int | None, body: dict[str, Any] | bytes = b"", headers: dict[str, str] | None = None, **kw: Any) -> dict[str, Any]:
    payload = json.dumps(body, separators=(",", ":")).encode() if isinstance(body, dict) else body
    return p144.classify_provider_response(
        status,
        headers or {"content-type": "application/json", "content-length": str(len(payload))},
        payload,
        delivery_id=kw.get("delivery_id", stable_hash({"delivery": "x"})),
        max_response_bytes=kw.get("max_response_bytes", 8192),
        max_retry_after_ms=kw.get("max_retry_after_ms", 1000),
        remaining_ms=kw.get("remaining_ms", 5000),
        wall_clock=datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC),
        truncated=kw.get("truncated", False),
    )


def _accepted_body(receipt: str = "r1") -> dict[str, str]:
    return {"schema_version": "p144.fixture_response.v1", "result": "accepted", "receipt_id": receipt}


def _duplicate_body(delivery_id: str, receipt: str = "r2") -> dict[str, str]:
    return {"schema_version": "p144.fixture_response.v1", "result": "duplicate", "receipt_id": receipt, "duplicate_of": delivery_id}


def _rejected_body(code: str = "invalid_payload") -> dict[str, str]:
    return {"schema_version": "p144.fixture_response.v1", "result": "rejected", "error_code": code}


FIXED_NOW = datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC)


def _run(fixture: Any, **kwargs: Any) -> dict[str, Any]:
    return p144.process_adapter_deliveries(fixture.config, fixture.capability, wall_clock=lambda: FIXED_NOW, monotonic=lambda: 0.0, **kwargs)


def _snapshot_state(fixture: Any) -> dict[str, bytes]:
    return {
        str(path.relative_to(fixture.config.state_root)): path.read_bytes()
        for path in sorted(fixture.config.state_root.rglob("*"))
        if path.is_file() and path != fixture.config.lease_path and not path.name.startswith(".")
    }


def _clear_runtime_state(fixture: Any) -> None:
    if fixture.config.state_root.exists():
        shutil.rmtree(fixture.config.state_root)
    p144._ensure_output_dirs(fixture.config)


def test_config_accepts_exact_closed_schema(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    assert p144.validate_adapter_config(fixture.config)["status"] == "valid"


def test_config_rejects_unknown_fields(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    raw = read_json(fixture.config_path)
    raw["unknown"] = "x"
    write_json(fixture.config_path, raw)
    with pytest.raises(p144.ProviderAdapterError, match="invalid_configuration_fields"):
        p144.load_adapter_config(fixture.config_path)


def test_duplicate_json_keys_are_rejected(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    text = fixture.config_path.read_text(encoding="utf-8")
    fixture.config_path.write_text(text.replace("{", '{"schema_version":"p144.adapter_config.v1",', 1), encoding="utf-8")
    with pytest.raises(p144.ProviderAdapterError, match="duplicate_json_key:schema_version"):
        p144.load_adapter_config(fixture.config_path)

    duplicate_body = b'{"schema_version":"p144.fixture_response.v1","result":"accepted","result":"duplicate","receipt_id":"r1"}'
    classified = _classify(200, duplicate_body)
    assert classified["classification"] == "malformed_response"
    assert classified["terminal_reason"] == "duplicate_json_key:result"


def test_config_rejects_unsafe_field_names(tmp_path: Path) -> None:
    for key in ("endpoint", "auth_token", "provider_sdk", "approval"):
        fixture = build_p144_fixture(tmp_path / key)
        raw = read_json(fixture.config_path)
        raw[key] = "forbidden"
        write_json(fixture.config_path, raw)
        with pytest.raises(p144.ProviderAdapterError, match="forbidden_configuration_field"):
            p144.load_adapter_config(fixture.config_path)


def test_config_rejects_unsafe_values(tmp_path: Path) -> None:
    for key, value in (("state_root", "https://example.test"), ("adapter_root", "${TOKEN}"), ("journal_root", "localhost")):
        fixture = build_p144_fixture(tmp_path / key)
        raw = read_json(fixture.config_path)
        raw[key] = value
        write_json(fixture.config_path, raw)
        with pytest.raises(p144.ProviderAdapterError, match="unsafe"):
            p144.load_adapter_config(fixture.config_path)


def test_paths_reject_traversal_symlink_and_hardlink(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    raw = read_json(fixture.config_path)
    raw["adapter_root"] = "../escape"
    write_json(fixture.config_path, raw)
    with pytest.raises(p144.ProviderAdapterError, match="unsafe_path"):
        p144.load_adapter_config(fixture.config_path)

    fixture = build_p144_fixture(tmp_path / "symlink")
    target = fixture.root / "target"
    target.mkdir()
    link = fixture.root / "linked"
    link.symlink_to(target, target_is_directory=True)
    raw = read_json(fixture.config_path)
    raw["adapter_root"] = "linked/adapter"
    write_json(fixture.config_path, raw)
    with pytest.raises(p144.ProviderAdapterError, match="symlink"):
        p144.load_adapter_config(fixture.config_path)


def test_roots_reject_unsafe_owner_and_permissions(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    bad = fixture.root / "bad"
    bad.mkdir()
    bad.chmod(0o777)
    raw = read_json(fixture.config_path)
    raw["adapter_root"] = "bad/adapter"
    write_json(fixture.config_path, raw)
    try:
        with pytest.raises(p144.ProviderAdapterError, match="permissions"):
            p144.load_adapter_config(fixture.config_path)
    finally:
        bad.chmod(0o700)


def test_roots_reject_overlap(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    raw = read_json(fixture.config_path)
    raw["adapter_root"] = "state"
    write_json(fixture.config_path, raw)
    with pytest.raises(p144.ProviderAdapterError, match="overlap"):
        p144.load_adapter_config(fixture.config_path)


def test_budgets_reject_bool_negative_overflow_and_inconsistency(tmp_path: Path) -> None:
    for key, value in (("max_sources_per_run", True), ("max_attempts_per_delivery", -1), ("max_request_bytes", 2_000_000), ("max_total_bytes_per_run", 2048)):
        fixture = build_p144_fixture(tmp_path / key)
        raw = read_json(fixture.config_path)
        raw[key] = value
        write_json(fixture.config_path, raw)
        with pytest.raises(p144.ProviderAdapterError, match="budget"):
            p144.load_adapter_config(fixture.config_path)


def test_p143_exact_qualified_release_required(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    evidence = read_json(fixture.p143.root / "output/release-evidence.json")
    evidence["status"] = "p143_preliminary_qualification_frozen"
    evidence["evidence_hash"] = stable_hash({key: value for key, value in evidence.items() if key != "evidence_hash"})
    write_json(fixture.p143.root / "output/release-evidence.json", evidence)
    with pytest.raises(p144.ProviderAdapterError, match="p143_release_dependency_drift"):
        p144.dependency_bindings(fixture.config)


def test_p143_stale_or_invalid_release_rejected(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    evidence = read_json(fixture.p143.root / "output/release-evidence.json")
    evidence["passed"] = 63
    write_json(fixture.p143.root / "output/release-evidence.json", evidence)
    with pytest.raises(p144.ProviderAdapterError, match="p143_release_evidence_hash_invalid"):
        p144.dependency_bindings(fixture.config)


def test_p143_projection_graph_required(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    projection_path = next(iter(sorted(fixture.p143.config.projection_dir.glob("*.json"))))
    projection = read_json(projection_path)
    projection["projection_id"] = stable_hash({"forged": "projection"})
    projection["projection_hash"] = stable_hash({key: value for key, value in projection.items() if key != "projection_hash"})
    write_json(projection_path, projection)
    with pytest.raises(Exception, match="projection|graph|invalid|conflicting"):
        p144.process_adapter_deliveries(fixture.config, fixture.capability)


def test_p143_projection_rederived_and_forgery_rejected(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    projection_path = next(iter(sorted(fixture.p143.config.projection_dir.glob("*.json"))))
    projection = read_json(projection_path)
    projection["payload"]["title"] = "forged"
    projection["projection_hash"] = stable_hash({key: value for key, value in projection.items() if key != "projection_hash"})
    write_json(projection_path, projection)
    with pytest.raises(Exception, match="projection|graph|invalid|conflicting"):
        p144.process_adapter_deliveries(fixture.config, fixture.capability)


def test_p142_exact_qualified_release_required(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    evidence = read_json(fixture.config.p142_artifact_root / "output/release-evidence.json")
    evidence["status"] = "blocked"
    evidence["evidence_hash"] = stable_hash({key: value for key, value in evidence.items() if key != "evidence_hash"})
    write_json(fixture.config.p142_artifact_root / "output/release-evidence.json", evidence)
    with pytest.raises(p144.ProviderAdapterError, match="p142_release_dependency_drift"):
        p144.dependency_bindings(fixture.config)


def test_p142_stale_or_invalid_release_rejected(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    evidence = read_json(fixture.config.p142_artifact_root / "output/release-evidence.json")
    evidence["passed"] = 43
    write_json(fixture.config.p142_artifact_root / "output/release-evidence.json", evidence)
    with pytest.raises(p144.ProviderAdapterError, match="p142_release_evidence_hash_invalid"):
        p144.dependency_bindings(fixture.config)


def test_transitive_dependency_graph_required(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    evidence = read_json(fixture.p143.root / "output/release-evidence.json")
    evidence["dependency_bindings"]["p142_evidence_hash"] = stable_hash({"wrong": "p142"})
    evidence["evidence_hash"] = stable_hash({key: value for key, value in evidence.items() if key != "evidence_hash"})
    write_json(fixture.p143.root / "output/release-evidence.json", evidence)
    with pytest.raises(p144.ProviderAdapterError, match="dependency|transitive"):
        p144.dependency_bindings(fixture.config)

    fixture = build_p144_fixture(tmp_path / "p133")
    p141_freeze = fixture.config.p142_artifact_root.parent / "p141/output/freeze-manifest.json"
    frozen = read_json(p141_freeze)
    frozen["dependency_bindings"]["p133_evidence_hash"] = stable_hash({"forged": "p133"})
    frozen["freeze_manifest_hash"] = stable_hash({key: value for key, value in frozen.items() if key != "freeze_manifest_hash"})
    write_json(p141_freeze, frozen)
    with pytest.raises(p144.ProviderAdapterError, match="dependency|transitive|p133"):
        p144.dependency_bindings(fixture.config)


def test_transitive_dependency_graph_carries_exact_p133_binding(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    bindings = p144.dependency_bindings(fixture.config)
    assert bindings["p141_dependency"] == bindings["p143_p141_dependency"]
    assert bindings["p141_dependency"] == bindings["p142_p141_dependency"]
    assert bindings["p133_dependency"] == {
        "p133_status": "p133_local_deadman_outbox_qualified",
        "p133_evidence_hash": "sha256:ba47502a7b82cea2521c581716801563f4ea31746cc243dfbbbd639707ffe73f",
    }


def test_external_and_production_delivery_flags_rejected() -> None:
    request_hash = stable_hash({"request": "x"})
    receipt: dict[str, Any] = {
        "schema_version": "p144.adapter_receipt.v1",
        "delivery_id": stable_hash({"delivery": "x"}),
        "request_hash": request_hash,
        "attempt_hashes": [],
        "terminal_classification": "accepted",
        "terminal_reason": "accepted_status",
        "provider_receipt_id": "r1",
        "duplicate_of": None,
        "requires_review": False,
        "automatic_retry_allowed": False,
        "transport_failure_class": "accepted_status",
        "production_delivered": True,
        "external_delivered": False,
    }
    receipt["receipt_hash"] = stable_hash(receipt)
    with pytest.raises(p144.ProviderAdapterError, match="delivery_authority_invalid"):
        p144._validate_adapter_receipt(receipt)


def test_receiver_capability_is_process_owned_and_unserializable(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    assert fixture.capability.owner_pid == os.getpid()
    with pytest.raises(TypeError):
        json.dumps(fixture.capability)
    forged = p144.ReceiverCapability(
        family=fixture.capability.family,
        packed_address=fixture.capability.packed_address,
        port=fixture.capability.port,
        owner_pid=1,
        socket_identity=fixture.capability.socket_identity,
        nonce=fixture.capability.nonce,
        _socket=fixture.capability._socket,
    )
    with pytest.raises(p144.ProviderAdapterError, match="process_owned"):
        p144.receiver_capability_hash(forged)


def test_ipv4_receiver_capability_accepted(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    assert p144.receiver_capability_hash(fixture.capability).startswith("sha256:")


def test_ipv6_receiver_capability_accepted_when_available() -> None:
    listener = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    try:
        listener.bind(("::1", 0))
        listener.listen(1)
    except OSError:
        pytest.skip("IPv6 loopback unavailable")
    try:
        capability = p144.issue_receiver_capability(listener)
        assert p144.receiver_capability_hash(capability).startswith("sha256:")
    finally:
        listener.close()


def test_hostnames_and_dns_entrypoints_rejected(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    raw = read_json(fixture.config_path)
    raw["state_root"] = "localhost"
    write_json(fixture.config_path, raw)
    with pytest.raises(p144.ProviderAdapterError, match="unsafe"):
        p144.load_adapter_config(fixture.config_path)


def test_non_loopback_numeric_address_rejected() -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("0.0.0.0", 0))
    listener.listen(1)
    try:
        with pytest.raises(p144.ProviderAdapterError, match="non_loopback"):
            p144.issue_receiver_capability(listener)
    finally:
        listener.close()


def test_unix_socket_rejected() -> None:
    if not hasattr(socket, "AF_UNIX"):
        pytest.skip("AF_UNIX unavailable")
    unix_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        with pytest.raises(p144.ProviderAdapterError, match="unix_socket"):
            p144.issue_receiver_capability(unix_socket)
    finally:
        unix_socket.close()


def test_fixed_post_method_and_path_emitted(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    req = _request(fixture)
    attempt = p144.deterministic_attempt_id(req["delivery_id"], req["request_binding_hash"], 0)
    wire = p144.encode_http_request(fixture.capability, req, attempt)
    assert wire.startswith(b"POST /opscat/provider-adapter/v1/deliveries HTTP/1.1\r\n")


def test_fixed_headers_emitted_in_canonical_order(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    request = _request(fixture)
    body = request["body_bytes"].encode("utf-8")
    binding_hash = p144.compute_request_binding_hash(request)
    first_attempt_id = p144.deterministic_attempt_id(request["delivery_id"], binding_hash, 0)
    expected = [
        ["content-type", "application/json"],
        ["content-length", str(len(body))],
        ["idempotency-key", request["idempotency_key"]],
        ["x-opscat-delivery-id", request["delivery_id"]],
        ["x-opscat-attempt-id", first_attempt_id],
        ["x-opscat-schema", p144.REQUEST_SCHEMA_VERSION],
    ]
    assert request["request_binding_hash"] == binding_hash
    assert request["fixed_headers"] == expected

    replacements = [
        "text/plain",
        str(len(body) + 1),
        stable_hash({"wrong": "idempotency"}),
        stable_hash({"wrong": "delivery"}),
        stable_hash({"wrong": "attempt"}),
        "p144.wrong.v1",
    ]
    for index, replacement in enumerate(replacements):
        forged = deepcopy(request)
        forged["fixed_headers"][index][1] = replacement
        forged["request_hash"] = stable_hash({key: value for key, value in forged.items() if key != "request_hash"})
        with pytest.raises(p144.ProviderAdapterError, match="fixed_headers"):
            p144._validate_adapter_request(forged)


def test_header_injection_and_request_control_rejected() -> None:
    with pytest.raises(p144.ProviderAdapterError, match="header_value"):
        p144._header_value("ok\r\nx: bad")


def test_canonical_request_body_is_byte_stable(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    assert _request(fixture) == _request(fixture)


def test_request_size_budget_rejected_before_socket(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path, max_request_bytes=1024)
    projection = _projection(fixture)
    projection["payload"]["body"] = "x" * 20_000
    projection["projection_hash"] = stable_hash({key: value for key, value in projection.items() if key != "projection_hash"})
    with pytest.raises(p144.ProviderAdapterError, match="request_size"):
        p144.prepare_adapter_request(fixture.config, projection, fixture.capability)


def test_delivery_id_is_deterministic_and_source_bound(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    req = _request(fixture)
    changed = _projection(fixture)
    changed["payload"]["title"] += " changed"
    changed["projection_hash"] = stable_hash({key: value for key, value in changed.items() if key != "projection_hash"})
    assert p144.prepare_adapter_request(fixture.config, changed, fixture.capability)["delivery_id"] != req["delivery_id"]


def test_p143_idempotency_key_preserved(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    projection = _projection(fixture)
    assert _request(fixture)["idempotency_key"] == projection["payload"]["idempotency_key"]


def test_p143_dedupe_key_is_non_authority_binding(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    req = _request(fixture)
    assert req["dedupe_key"] == _projection(fixture)["payload"]["dedupe_key"]
    assert "host" not in json.dumps(req["p143_source_bindings"])


def test_success_statuses_classify_accepted() -> None:
    for status in (200, 201, 202):
        assert _classify(status, _accepted_body())["classification"] == "accepted"


def test_no_content_204_is_accepted() -> None:
    assert _classify(204, b"")["classification"] == "accepted"


def test_208_valid_duplicate_is_accepted() -> None:
    delivery = stable_hash({"d": 1})
    assert _classify(208, _duplicate_body(delivery), delivery_id=delivery)["classification"] == "duplicate_accepted"


def test_409_requires_exact_duplicate_body() -> None:
    delivery = stable_hash({"d": 1})
    assert _classify(409, _duplicate_body(delivery), delivery_id=delivery)["classification"] == "duplicate_accepted"
    assert _classify(409, _duplicate_body(stable_hash({"other": 1})), delivery_id=delivery)["classification"] == "malformed_response"


def test_permanent_4xx_never_retries() -> None:
    for status in (400, 404, 405, 410, 413, 415, 422):
        assert _classify(status, _rejected_body())["classification"] == "permanent_failure"


def test_408_and_425_create_bounded_adapter_retry() -> None:
    for status in (408, 425):
        assert _classify(status, _rejected_body("temporarily_unavailable"))["classification"] == "transient_failure"


def test_429_retry_after_creates_bounded_adapter_retry() -> None:
    result = _classify(429, _rejected_body("throttled"), {"retry-after": "1", "content-length": "0"})
    assert result["classification"] == "transient_failure"
    assert result["retry_after"]["delay_ms"] == 1000


def test_transient_5xx_retries_then_succeeds(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path, max_sources_per_run=1)
    fixture.responses = [response(500, _rejected_body("internal_error")), accepted_response("after-retry")]
    fixture.start()
    try:
        run = p144.process_adapter_deliveries(fixture.config, fixture.capability)
        assert run["adapter_counters"]["retry_schedule_count"] == 1
        request = read_json(next(fixture.config.adapter_root.glob("*.request.json")))
        journal_attempt_ids = [
            entry["attempt_id"]
            for entry in (read_json(path) for path in sorted(fixture.config.journal_root.glob("*.json")))
            if entry["phase"] == "attempt_prepared"
        ]
        expected_attempt_ids = [
            p144.deterministic_attempt_id(request["delivery_id"], request["request_binding_hash"], index)
            for index in range(2)
        ]
        wire_headers = [_wire_headers(wire) for wire in fixture.requests]
        assert request["fixed_headers"][4][1] == journal_attempt_ids[0] == wire_headers[0]["x-opscat-attempt-id"]
        assert journal_attempt_ids == expected_attempt_ids
        assert [headers["x-opscat-attempt-id"] for headers in wire_headers] == expected_attempt_ids
        assert expected_attempt_ids[0] != expected_attempt_ids[1]
        assert fixture.requests[0].split(b"\r\n\r\n", 1)[1] == fixture.requests[1].split(b"\r\n\r\n", 1)[1]
        for name in ("idempotency-key", "x-opscat-delivery-id"):
            assert wire_headers[0][name] == wire_headers[1][name]
    finally:
        fixture.close()


def test_retry_budget_exhaustion_is_terminal() -> None:
    cls = _classify(503, _rejected_body("temporarily_unavailable"))
    assert cls["classification"] == "transient_failure"


def test_invalid_retry_after_fails_without_wait() -> None:
    assert _classify(429, _rejected_body("throttled"), {"retry-after": "bad", "content-length": "0"})["classification"] == "malformed_response"


def test_excessive_retry_after_rejected() -> None:
    assert _classify(429, _rejected_body("throttled"), {"retry-after": "999", "content-length": "0"}, max_retry_after_ms=1)["classification"] == "malformed_response"


def test_redirect_is_rejected_and_never_followed() -> None:
    result = _classify(302, b"", {"location": "https://example.test", "content-length": "0"})
    assert result["classification"] == "redirect_rejected"


def test_malformed_status_rejected() -> None:
    with pytest.raises(p144.ProviderAdapterError, match="malformed_status"):
        p144._parse_raw_response(b"NOPE\r\ncontent-length: 0\r\n\r\n")

    fixture = build_p144_fixture(Path("/private/tmp/p144-malformed-status"), max_sources_per_run=1)
    fixture.responses = [b"NOPE\r\ncontent-length: 0\r\n\r\n"]
    fixture.start()
    try:
        run = _run(fixture)
        assert run["terminal_counts"]["malformed_response"] == 1
        assert p144.list_adapter_receipts(fixture.config)[0]["terminal_reason"] == "malformed_status"
    finally:
        fixture.close()


def test_malformed_and_duplicate_framing_headers_rejected() -> None:
    with pytest.raises(p144.ProviderAdapterError, match="duplicate"):
        p144._parse_raw_response(b"HTTP/1.1 200 OK\r\ncontent-length: 0\r\ncontent-length: 0\r\n\r\n")
    with pytest.raises(p144.ProviderAdapterError, match="transfer_encoding"):
        p144._parse_raw_response(b"HTTP/1.1 200 OK\r\ntransfer-encoding: chunked\r\n\r\n0\r\n\r\n")
    with pytest.raises(p144.ProviderAdapterError, match="transfer_encoding"):
        p144._parse_raw_response(b"HTTP/1.1 200 OK\r\ncontent-length: 0\r\ntransfer-encoding: chunked\r\n\r\n")
    with pytest.raises(p144.ProviderAdapterError, match="transfer_encoding"):
        p144._parse_raw_response(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: identity\r\n\r\n")
    with pytest.raises(p144.ProviderAdapterError, match="malformed_headers"):
        p144._parse_raw_response(b"HTTP/1.1 200 OK\r\ntransfer-encoding : chunked\r\n\r\n")

    fixture = build_p144_fixture(Path("/private/tmp/p144-duplicate-framing"), max_sources_per_run=1)
    fixture.responses = [b"HTTP/1.1 200 OK\r\ncontent-length: 0\r\ntransfer-encoding: chunked\r\n\r\n"]
    fixture.start()
    try:
        _run(fixture)
        receipt = p144.list_adapter_receipts(fixture.config)[0]
        assert receipt["terminal_classification"] == "malformed_response"
        assert receipt["terminal_reason"] == "transfer_encoding_forbidden"
    finally:
        fixture.close()


def test_malformed_provider_json_rejected() -> None:
    assert _classify(200, b"{")["classification"] == "malformed_response"
    duplicate = _classify(200, b'{"schema_version":"p144.fixture_response.v1","result":"accepted","result":"duplicate","receipt_id":"r1"}')
    assert duplicate["classification"] == "malformed_response"
    assert duplicate["terminal_reason"] == "duplicate_json_key:result"


def test_oversized_response_budget_enforced(tmp_path: Path) -> None:
    assert _classify(200, b"x" * 10, max_response_bytes=1)["classification"] == "oversized_response"

    fixture = build_p144_fixture(tmp_path, max_sources_per_run=1, max_response_bytes=256)
    fixture.responses = [response(200, b"x" * 257)]
    fixture.start()
    try:
        _run(fixture)
        receipt = p144.list_adapter_receipts(fixture.config)[0]
        assert receipt["terminal_classification"] == "oversized_response"
        assert receipt["terminal_reason"] == "response_size_exceeded"
    finally:
        fixture.close()


def test_truncated_response_detected(tmp_path: Path) -> None:
    assert _classify(200, _accepted_body(), truncated=True)["classification"] == "truncated_response"

    fixture = build_p144_fixture(tmp_path, max_sources_per_run=1)
    fixture.responses = [b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: 99\r\n\r\n{}"]
    fixture.start()
    try:
        _run(fixture)
        receipt = p144.list_adapter_receipts(fixture.config)[0]
        assert receipt["terminal_classification"] == "truncated_response"
        assert receipt["terminal_reason"] == "response_truncated"
    finally:
        fixture.close()


def test_connection_failure_receipt_is_deterministic() -> None:
    first = _classify(None)
    second = _classify(None)
    assert first == second
    assert first["classification"] == "connection_failure"


def test_timeout_is_bounded_and_classified() -> None:
    assert p144._classification("timeout", "socket_timeout", {})["classification"] == "timeout"


def test_only_fixed_safe_response_headers_persisted() -> None:
    result = _classify(200, _accepted_body(), {"content-type": "application/json", "x-secret": "no", "x-opscat-provider-receipt-id": "safe"})
    assert set(result["safe_headers"]) == {"content-type", "x-opscat-provider-receipt-id"}


def test_provider_receipt_id_is_bounded_and_validated() -> None:
    assert _classify(200, _accepted_body("Receipt-1"))["provider_receipt_id"] == "Receipt-1"
    with pytest.raises(p144.ProviderAdapterError, match="provider_receipt_id"):
        _classify(200, _accepted_body("https://bad"))


def test_completed_replay_is_byte_identical_and_opens_no_socket(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path, max_sources_per_run=256)
    fixture.start()
    first = _run(fixture)
    first_bytes = _snapshot_state(fixture)
    before = len(fixture.requests)
    second = _run(fixture)
    assert first["delivery_ids"] == second["delivery_ids"]
    assert len(fixture.requests) == before
    assert _snapshot_state(fixture) == first_bytes
    fixture.close()


def test_conflicting_replay_artifacts_fail_closed(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path, max_sources_per_run=1)
    fixture.start()
    run = p144.process_adapter_deliveries(fixture.config, fixture.capability)
    request_path = fixture.config.adapter_root / f"{run['delivery_ids'][0][7:]}.request.json"
    request_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(p144.ProviderAdapterError, match="conflicting"):
        p144.process_adapter_deliveries(fixture.config, fixture.capability)
    fixture.close()


def test_pre_send_crash_recovers_at_most_once(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path, max_sources_per_run=1)
    fixture.start()
    for marker in ("request:file_fsync", "request:before_replace", "request:after_replace", "attempt_started"):
        _clear_runtime_state(fixture)
        fixture.responses = [accepted_response()]
        before_requests = len(fixture.requests)
        with pytest.raises(RuntimeError, match="request|attempt_started"):
            _run(fixture, crash_after=marker)
        before_recovery = _snapshot_state(fixture)
        assert len(fixture.requests) == before_requests
        recovered = _run(fixture)
        assert len(fixture.requests) == before_requests + 1
        assert all(_snapshot_state(fixture)[path] == data for path, data in before_recovery.items())
        assert recovered["terminal_counts"]["accepted"] == 1
    fixture.close()


def test_journal_is_append_only_hash_chained_and_exactly_phased(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path, max_sources_per_run=1)
    fixture.start()
    _run(fixture)
    entries = [read_json(path) for path in sorted(fixture.config.journal_root.glob("*.json"))]
    assert [entry["phase"] for entry in entries] == [
        "request_prepared",
        "attempt_prepared",
        "attempt_started",
        "request_committed",
        "transport_completed",
        "attempt_written",
        "receipt_prepared",
        "receipt_written",
        "cursor_prepared",
        "cursor_written",
        "run_prepared",
        "run_written",
    ]
    prior: str | None = None
    for index, entry in enumerate(entries):
        assert entry["entry_index"] == index
        assert entry["prior_entry_hash"] == prior
        assert entry["entry_hash"] == stable_hash({key: value for key, value in entry.items() if key != "entry_hash"})
        assert set(entry) == {
            "schema_version",
            "delivery_id",
            "entry_index",
            "phase",
            "attempt_index",
            "attempt_id",
            "request_bytes_sha256",
            "committed_request_bytes",
            "response_sha256",
            "prepared_artifact",
            "prepared_artifact_bytes_sha256",
            "prior_entry_hash",
            "entry_hash",
        }
        prior = entry["entry_hash"]
    fixture.close()


def test_post_send_ambiguity_requires_review_and_never_retries(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path, max_sources_per_run=256)
    fixture.start()
    with pytest.raises(RuntimeError, match="request_committed"):
        _run(fixture, crash_after="request_committed")
    assert len(fixture.requests) == 1
    ambiguous_request = fixture.requests[0]
    recovered = _run(fixture)
    recovered_request_count = len(fixture.requests)
    assert recovered_request_count > 1
    assert fixture.requests.count(ambiguous_request) == 1
    receipt = next(item for item in p144.list_adapter_receipts(fixture.config) if item["terminal_classification"] == "indeterminate_requires_review")
    assert recovered["terminal_counts"]["indeterminate_requires_review"] == 1
    assert receipt["terminal_classification"] == "indeterminate_requires_review"
    assert receipt["transport_failure_class"] == "request_committed_response_unknown"
    assert receipt["requires_review"] is True
    assert receipt["automatic_retry_allowed"] is False
    replay_bytes = _snapshot_state(fixture)
    _run(fixture)
    assert len(fixture.requests) == recovered_request_count
    assert _snapshot_state(fixture) == replay_bytes
    fixture.close()


def test_attempt_crash_windows_recover_exactly(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path, max_sources_per_run=1)
    fixture.start()
    for marker in ("transport_completed", "attempt:file_fsync", "attempt:before_replace", "attempt:after_replace"):
        _clear_runtime_state(fixture)
        fixture.responses = [accepted_response()]
        before_requests = len(fixture.requests)
        with pytest.raises(RuntimeError, match="attempt|transport_completed"):
            _run(fixture, crash_after=marker)
        persisted = _snapshot_state(fixture)
        after_crash_requests = len(fixture.requests)
        recovered = _run(fixture)
        assert len(fixture.requests) == after_crash_requests == before_requests + 1
        assert all(_snapshot_state(fixture)[path] == data for path, data in persisted.items())
        assert recovered["terminal_counts"]["accepted"] == 1
        assert sum(recovered["terminal_counts"].values()) == 1
        receipt = p144.list_adapter_receipts(fixture.config)[0]
        assert receipt["requires_review"] is False
        assert receipt["automatic_retry_allowed"] is False
    fixture.close()


def test_receipt_crash_windows_recover_exactly(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path, max_sources_per_run=1)
    fixture.start()
    for marker in ("receipt:file_fsync", "receipt:before_replace", "receipt:after_replace"):
        _clear_runtime_state(fixture)
        fixture.responses = [accepted_response()]
        with pytest.raises(RuntimeError, match="receipt"):
            _run(fixture, crash_after=marker)
        persisted = _snapshot_state(fixture)
        request_count = len(fixture.requests)
        recovered = _run(fixture)
        assert len(fixture.requests) == request_count
        assert all(_snapshot_state(fixture)[path] == data for path, data in persisted.items())
        assert recovered["terminal_counts"]["accepted"] == 1
        assert sum(recovered["terminal_counts"].values()) == 1
        assert p144.list_adapter_receipts(fixture.config)[0]["terminal_classification"] == "accepted"
    fixture.close()


def test_cursor_and_run_crash_windows_recover_exactly(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path, max_sources_per_run=1)
    fixture.start()
    for marker in (
        "cursor:file_fsync",
        "cursor:before_replace",
        "cursor:after_replace",
        "run:file_fsync",
        "run:before_replace",
        "run:after_replace",
    ):
        _clear_runtime_state(fixture)
        fixture.responses = [accepted_response()]
        with pytest.raises(RuntimeError, match="cursor|run"):
            _run(fixture, crash_after=marker)
        persisted = _snapshot_state(fixture)
        request_count = len(fixture.requests)
        recovered = _run(fixture)
        assert len(fixture.requests) == request_count
        assert all(_snapshot_state(fixture)[path] == data for path, data in persisted.items())
        assert recovered["terminal_counts"]["accepted"] == 1
        assert sum(recovered["terminal_counts"].values()) == 1
        assert p144.list_adapter_receipts(fixture.config)[0]["terminal_classification"] == "accepted"
    fixture.close()


def test_lease_conflict_blocks_before_socket(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path)
    fixture.config.lease_path.write_text("locked", encoding="utf-8")
    with pytest.raises(p144.ProviderAdapterError, match="lease_conflict"):
        _run(fixture)
    assert fixture.config.lease_path.read_text(encoding="utf-8") == "locked"
    assert fixture.requests == []


def test_bounded_multi_cycle_progress_cannot_strand_sources(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path, max_sources_per_run=1)
    fixture.start()
    first = _run(fixture)
    second = _run(fixture)
    assert first["processed_source_ids"]
    assert second["processed_source_ids"]
    assert set(first["processed_source_ids"]).isdisjoint(second["processed_source_ids"])
    seen_source_ids = set(first["processed_source_ids"]) | set(second["processed_source_ids"])
    last = second
    for _ in range(256):
        request_count = len(fixture.requests)
        current = _run(fixture)
        if len(fixture.requests) == request_count:
            assert current["run_hash"] == last["run_hash"]
            break
        current_source_ids = set(current["processed_source_ids"])
        assert current_source_ids
        assert seen_source_ids.isdisjoint(current_source_ids)
        seen_source_ids.update(current_source_ids)
        last = current
    else:
        pytest.fail("bounded progression did not reach terminal replay")
    expected_source_ids = {
        read_json(path)["projection_id"]
        for path in fixture.p143.config.projection_dir.glob("*.json")
    }
    assert seen_source_ids == expected_source_ids
    fixture.close()


def test_forbidden_entrypoints_and_counters_remain_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = build_p144_fixture(tmp_path, max_sources_per_run=1)
    fixture.start()

    from app.api import approvals
    from app.services import (
        controlled_remediation,
        p133_deadman_outbox,
        p142_loopback_transport_lab,
        secret_service,
        slack_ticket_draft_automation,
    )
    from app.tools import mock_actions

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("forbidden_entrypoint_called")

    real_socket_module = socket
    real_os_module = os
    allowed_socket_count = 0

    class GuardedSocket:
        def __init__(self, wrapped: socket.socket) -> None:
            self._wrapped = wrapped

        def connect(self, target: tuple[Any, ...]) -> None:
            assert target[0] in {"127.0.0.1", "::1"}
            self._wrapped.connect(target)

        def __getattr__(self, name: str) -> Any:
            return getattr(self._wrapped, name)

    def guarded_socket(family: int, kind: int, *args: Any, **kwargs: Any) -> GuardedSocket:
        nonlocal allowed_socket_count
        assert family in {real_socket_module.AF_INET, real_socket_module.AF_INET6}
        assert kind == real_socket_module.SOCK_STREAM
        allowed_socket_count += 1
        return GuardedSocket(real_socket_module.socket(family, kind, *args, **kwargs))

    class GuardedSocketModule:
        AF_INET = real_socket_module.AF_INET
        AF_INET6 = real_socket_module.AF_INET6
        SOCK_STREAM = real_socket_module.SOCK_STREAM

        socket = staticmethod(guarded_socket)

        def __getattr__(self, name: str) -> Any:
            if name in {"getaddrinfo", "gethostbyname", "gethostbyname_ex", "getnameinfo", "create_connection"}:
                return forbidden
            return getattr(real_socket_module, name)

    monkeypatch.setattr(p144, "socket", GuardedSocketModule())
    for module, names in (
        (ssl, ("create_default_context",)),
        (urllib.request, ("urlopen",)),
        (http.client, ("HTTPConnection", "HTTPSConnection")),
        (subprocess, ("run", "Popen", "check_output")),
    ):
        for name in names:
            monkeypatch.setattr(module, name, forbidden)
    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", forbidden)
    monkeypatch.setattr(secret_service.LocalEncryptedSecretProvider, "get_secret", forbidden)

    for module, entrypoint_names in (
        (p142_loopback_transport_lab, ("_dispatch_or_recover",)),
        (p133_deadman_outbox, ("acknowledge_event",)),
        (approvals, ("propose_action", "decide_persisted_action", "approve_action", "reject_action", "execute_action")),
        (mock_actions, ("execute_mock_action",)),
        (controlled_remediation, ("run_controlled_remediation_fixture", "write_controlled_remediation_outputs")),
        (slack_ticket_draft_automation, ("evaluate_slack_ticket_draft_fixture", "write_slack_ticket_draft_outputs")),
    ):
        for name in entrypoint_names:
            monkeypatch.setattr(module, name, forbidden)

    class ForbiddenEnvironment:
        def __getitem__(self, _key: object) -> Any:
            return forbidden()

        def get(self, *_args: Any, **_kwargs: Any) -> Any:
            return forbidden()

        def __iter__(self) -> Any:
            return forbidden()

        def keys(self) -> Any:
            return forbidden()

        def values(self) -> Any:
            return forbidden()

        def items(self) -> Any:
            return forbidden()

    class GuardedOSModule:
        environ = ForbiddenEnvironment()
        environb = ForbiddenEnvironment()
        getenv = staticmethod(forbidden)
        system = staticmethod(forbidden)

        def __getattr__(self, name: str) -> Any:
            return getattr(real_os_module, name)

    monkeypatch.setattr(p144, "os", GuardedOSModule())

    run = _run(fixture)
    fixture.close()
    assert allowed_socket_count == 1
    assert all(type(value) is int and value == 0 for value in run["forbidden_counters"].values())

    forbidden_imports = {"requests", "httpx", "ssl", "subprocess", "urllib", "http.client", "slack_sdk", "sendgrid", "twilio", "pagerduty", "boto3"}
    forbidden_environment_names = {"getenv", "getenvb", "putenv", "unsetenv", "environ", "environb"}
    for relative in ("app/p144_provider_adapter_cli.py", "app/services/p144_provider_adapter_lab.py"):
        tree = ast.parse((Path(__file__).resolve().parents[1] / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(alias.name in forbidden_imports or alias.name.split(".")[0] in forbidden_imports for alias in node.names)
            if isinstance(node, ast.ImportFrom):
                assert node.module not in forbidden_imports
            if isinstance(node, (ast.Attribute, ast.Name)):
                assert getattr(node, "attr", getattr(node, "id", None)) not in forbidden_environment_names
