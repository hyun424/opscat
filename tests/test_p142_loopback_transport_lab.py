from __future__ import annotations

import hashlib
import json
import os
import socket
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import app.services.p142_loopback_transport_lab as p142
from app.services.p110_evaluation import stable_hash
from app.services.p142_loopback_transport_lab import (
    LoopbackTransportError,
    deterministic_attempt_id,
    deterministic_dispatch_id,
    load_loopback_transport_config,
    parse_loopback_authority,
    parse_retry_after,
    process_loopback_transport,
)
from tests.fixtures.p141.builders import write_json
from tests.fixtures.p142.builders import build_p142_fixture, read_json


def _emit_counter_marker(counters: dict[str, int]) -> None:
    print("P142_CASE_COUNTERS=" + json.dumps(counters, sort_keys=True, separators=(",", ":")))


def _sum_counter_maps(*values: dict[str, int]) -> dict[str, int]:
    result = p142.zero_transport_counters()
    for value in values:
        for key in result:
            result[key] += value[key]
    return result


def _observed_failure_counters(seen: list[dict[str, Any]]) -> dict[str, int]:
    counters = p142.zero_transport_counters()
    counters["loopback_socket_attempt_count"] = len(seen)
    counters["loopback_request_commit_count"] = len(seen)
    counters["loopback_request_byte_count"] = sum(len(item["request"]) for item in seen)
    counters["loopback_transport_failure_count"] = len(seen)
    return counters


@contextmanager
def http_sink(
    *,
    family: int = socket.AF_INET,
    status: int = 200,
    body: bytes = b"ok",
    headers: dict[str, str] | None = None,
    malformed: bool = False,
) -> Iterator[tuple[str, int, list[dict[str, Any]]]]:
    server = socket.socket(family, socket.SOCK_STREAM)
    address: tuple[Any, ...] = ("127.0.0.1", 0) if family == socket.AF_INET else ("::1", 0, 0, 0)
    server.bind(address)
    server.listen(8)
    host, port = server.getsockname()[:2]
    seen: list[dict[str, Any]] = []
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                server.settimeout(0.1)
                conn, peer = server.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            with conn:
                data = b""
                while b"\r\n\r\n" not in data:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                if b"Content-Length:" in data:
                    head = data.split(b"\r\n\r\n", 1)[0].decode("iso-8859-1")
                    length = 0
                    for line in head.split("\r\n"):
                        if line.lower().startswith("content-length:"):
                            length = int(line.split(":", 1)[1].strip())
                    while len(data.split(b"\r\n\r\n", 1)[1]) < length:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                seen.append({"peer": peer, "request": data})
                if malformed:
                    conn.sendall(b"not-http\r\n\r\n")
                    continue
                response_headers = {"Content-Length": str(len(body)), **(headers or {})}
                header_bytes = "".join(f"{key}: {value}\r\n" for key, value in response_headers.items()).encode("ascii")
                conn.sendall(f"HTTP/1.1 {status} test\r\n".encode("ascii") + header_bytes + b"\r\n" + body)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield str(host), int(port), seen
    finally:
        stop.set()
        server.close()
        thread.join(timeout=1)


def test_config_accepts_closed_numeric_loopback_routes(tmp_path: Path) -> None:
    with http_sink() as (host, port, _seen):
        fixture = build_p142_fixture(tmp_path, authority=f"{host}:{port}")
        assert fixture.config.schema_version == "p142.loopback_transport_config.v1"
        assert fixture.config.routes[0].parsed.family == socket.AF_INET
        assert parse_loopback_authority(f"127.42.0.9:{port}").address == "127.42.0.9"
    assert parse_loopback_authority("[::1]:65535").family == socket.AF_INET6


def test_config_rejects_unknown_and_authority_bearing_fields(tmp_path: Path) -> None:
    fixture = build_p142_fixture(tmp_path)
    raw = read_json(fixture.config_path)
    raw["webhook_url"] = "http://127.0.0.1:1"
    write_json(fixture.config_path, raw)
    with pytest.raises(LoopbackTransportError, match="forbidden_configuration_field"):
        load_loopback_transport_config(fixture.config_path)


def test_config_rejects_hostname_dns_and_localhost_targets(tmp_path: Path) -> None:
    for authority in ("localhost:80", "example.invalid:80", "[::1%lo0]:80", "::1:80"):
        with pytest.raises(LoopbackTransportError):
            build_p142_fixture(tmp_path / authority.replace("/", "_").replace(":", "_"), authority=authority)


def test_config_rejects_non_loopback_numeric_targets(tmp_path: Path) -> None:
    bad = ("10.0.0.1:80", "192.168.1.2:80", "8.8.8.8:53", "0.0.0.0:80", "127.0.0.0:80", "127.255.255.255:80", "[::ffff:127.0.0.1]:80", "0177.0.0.1:80")
    for authority in bad:
        with pytest.raises(LoopbackTransportError):
            build_p142_fixture(tmp_path / authority.replace("/", "_").replace(":", "_"), authority=authority)


def test_config_rejects_proxy_env_tls_auth_and_credentials(tmp_path: Path) -> None:
    for index, (key, value) in enumerate((("proxy", "http://127.0.0.1:1"), ("tls", True), ("auth_header", "Bearer secret"), ("credential", "secret"))):
        fixture = build_p142_fixture(tmp_path / f"case{index}")
        raw = read_json(fixture.config_path)
        raw[key] = value
        write_json(fixture.config_path, raw)
        with pytest.raises(LoopbackTransportError):
            load_loopback_transport_config(fixture.config_path)


def test_config_rejects_redirect_command_action_and_mutation_surfaces(tmp_path: Path) -> None:
    for index, key in enumerate(("redirect", "command", "action", "remediation", "production_mutation")):
        fixture = build_p142_fixture(tmp_path / f"case{index}")
        raw = read_json(fixture.config_path)
        raw[key] = "forbidden"
        write_json(fixture.config_path, raw)
        with pytest.raises(LoopbackTransportError):
            load_loopback_transport_config(fixture.config_path)


def test_path_symlink_hardlink_and_overlap_fail_closed(tmp_path: Path) -> None:
    assert build_p142_fixture(tmp_path / "tilde", path="/x~y").config.routes[0].path == "/x~y"
    for path in ("//x", "/./x", "/a/../b", "/has space", "/x%2f", "/x?y", "/x\\y", "/foo/", "/$HOME"):
        with pytest.raises(LoopbackTransportError):
            build_p142_fixture(tmp_path / path.replace("/", "_"), path=path)
    fixture = build_p142_fixture(tmp_path / "link")
    os.link(fixture.config_path, fixture.config_path.with_name("copy.json"))
    with pytest.raises(LoopbackTransportError, match="configuration_has_multiple_links"):
        load_loopback_transport_config(fixture.config_path)
    symlink = build_p142_fixture(tmp_path / "symlink")
    symlink.config.receipt_dir.rmdir()
    symlink.config.receipt_dir.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(LoopbackTransportError):
        process_loopback_transport(symlink.config)
    overlap = build_p142_fixture(tmp_path / "overlap")
    raw = read_json(overlap.config_path)
    raw["receipt_dir"] = raw["dispatch_dir"]
    write_json(overlap.config_path, raw)
    with pytest.raises(LoopbackTransportError, match="overlap|paths_overlap"):
        load_loopback_transport_config(overlap.config_path)


def test_config_rejects_tilde_and_environment_path_literals(tmp_path: Path) -> None:
    for index, (key, value) in enumerate(
        (
            ("p141_config_path", "~/p141.json"),
            ("p141_release_evidence_path", "$HOME/p141-release-evidence.json"),
            ("dispatch_dir", "~/dispatch"),
            ("journal_dir", "$P142_JOURNALS"),
            ("receipt_dir", "~/receipts"),
            ("cursor_path", "$HOME/cursor.json"),
            ("run_dir", "~/runs"),
        )
    ):
        fixture = build_p142_fixture(tmp_path / f"case{index}")
        raw = read_json(fixture.config_path)
        raw[key] = value
        write_json(fixture.config_path, raw)
        with pytest.raises(LoopbackTransportError, match="invalid_local_path"):
            load_loopback_transport_config(fixture.config_path)

    fixture = build_p142_fixture(tmp_path / "config-path")
    with pytest.raises(LoopbackTransportError, match="invalid_configuration_path"):
        load_loopback_transport_config(Path("~") / fixture.config_path.name)


def test_config_enforces_time_body_response_and_artifact_budgets(tmp_path: Path) -> None:
    for key, value in (("max_attempts", 0), ("max_request_bytes", 0), ("base_backoff_ms", 20)):
        fixture = build_p142_fixture(tmp_path / key)
        raw = read_json(fixture.config_path)
        raw[key] = value
        write_json(fixture.config_path, raw)
        with pytest.raises(LoopbackTransportError):
            load_loopback_transport_config(fixture.config_path)


def test_valid_p141_opened_envelope_dispatches_to_loopback(tmp_path: Path) -> None:
    with http_sink() as (host, port, seen):
        fixture = build_p142_fixture(tmp_path, authority=f"{host}:{port}")
        result = process_loopback_transport(fixture.config)
    _emit_counter_marker(result["transport_counters"])
    assert result["processed_envelope_count"] == 2
    assert result["receipt_count"] == 2
    assert len(seen) == 2
    assert all(b"Idempotency-Key: sha256:" in item["request"] for item in seen)


def test_all_p141_transition_envelopes_bind_before_dispatch(tmp_path: Path) -> None:
    with http_sink() as (host, port, _seen):
        fixture = build_p142_fixture(tmp_path, authority=f"{host}:{port}")
        result = process_loopback_transport(fixture.config)
    _emit_counter_marker(result["transport_counters"])
    receipts = [read_json(path) for path in sorted(fixture.config.receipt_dir.glob("*.json"))]
    assert result["receipt_count"] == 2
    assert {receipt["p141_binding"]["destination_id"] for receipt in receipts} == {"primary-operator", "backup-operator"}


def test_p141_hash_receipt_and_cursor_drift_fail_closed(tmp_path: Path) -> None:
    fixture = build_p142_fixture(tmp_path)
    envelope_path = next(fixture.p141.config.envelope_dir.glob("*.json"))
    envelope = read_json(envelope_path)
    envelope["message"]["title"] = "tampered"
    write_json(envelope_path, envelope)
    with pytest.raises(Exception, match="hash|binding|backed|contract"):
        process_loopback_transport(fixture.config)


def test_p141_cross_config_rewind_gap_and_fork_fail_closed(tmp_path: Path) -> None:
    fixture = build_p142_fixture(tmp_path)
    evidence = read_json(fixture.p141_release_evidence_path)
    evidence["status"] = "blocked"
    evidence["evidence_hash"] = stable_hash({key: value for key, value in evidence.items() if key != "evidence_hash"})
    write_json(fixture.p141_release_evidence_path, evidence)
    with pytest.raises(LoopbackTransportError, match="not_qualified|hash_drift"):
        process_loopback_transport(fixture.config)


def test_p141_and_p133_artifacts_are_immutable_except_exact_public_reader_leases(tmp_path: Path) -> None:
    with http_sink() as (host, port, _seen):
        fixture = build_p142_fixture(tmp_path, authority=f"{host}:{port}")
        before = _tree_bytes(fixture.p141.root)
        result = process_loopback_transport(fixture.config)
        after = _tree_bytes(fixture.p141.root)
    _emit_counter_marker(result["transport_counters"])
    assert after == before


def test_real_ipv4_loopback_http_dispatch_writes_receipt(tmp_path: Path) -> None:
    with http_sink(family=socket.AF_INET, body=b"ipv4") as (host, port, _seen):
        fixture = build_p142_fixture(tmp_path, authority=f"{host}:{port}")
        result = process_loopback_transport(fixture.config)
    _emit_counter_marker(result["transport_counters"])
    receipt = read_json(next(fixture.config.receipt_dir.glob("*.json")))
    assert result["transport_counters"]["loopback_socket_attempt_count"] == 2
    assert receipt["delivered_to_loopback"] is True
    assert receipt["production_delivered"] is False
    assert receipt["acknowledged"] is False


def test_real_ipv6_loopback_http_dispatch_writes_receipt(tmp_path: Path) -> None:
    try:
        with http_sink(family=socket.AF_INET6, body=b"ipv6") as (_host, port, _seen):
            fixture = build_p142_fixture(tmp_path, authority=f"[::1]:{port}")
            result = process_loopback_transport(fixture.config)
    except OSError:
        pytest.skip("IPv6 loopback unavailable")
    _emit_counter_marker(result["transport_counters"])
    assert result["transport_counters"]["loopback_socket_attempt_count"] == 2


def test_socket_cannot_open_before_numeric_loopback_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def fail_socket(*_args: Any, **_kwargs: Any) -> socket.socket:
        nonlocal calls
        calls += 1
        raise AssertionError("socket opened")

    monkeypatch.setattr(p142.socket, "socket", fail_socket)
    with pytest.raises(LoopbackTransportError):
        build_p142_fixture(tmp_path, authority="example.invalid:80")
    assert calls == 0


def test_dns_env_proxy_and_provider_entrypoints_are_never_called(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with http_sink() as (host, port, _seen):
        fixture = build_p142_fixture(tmp_path, authority=f"{host}:{port}")
        monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("dns")))
        monkeypatch.setattr(socket, "create_connection", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("helper")))
        result = process_loopback_transport(fixture.config)
    _emit_counter_marker(result["transport_counters"])


def test_redirect_response_is_recorded_not_followed(tmp_path: Path) -> None:
    with http_sink(status=302, headers={"Location": "http://example.invalid/"}) as (host, port, seen):
        fixture = build_p142_fixture(tmp_path, authority=f"{host}:{port}")
        result = process_loopback_transport(fixture.config)
    _emit_counter_marker(result["transport_counters"])
    receipt = read_json(next(fixture.config.receipt_dir.glob("*.json")))
    assert len(seen) == 2
    assert receipt["status_code"] == 302
    assert receipt["delivered_to_loopback"] is False
    assert receipt["transport_counters"]["loopback_http_3xx_count"] == 1


def test_response_body_budget_and_truncation_are_bounded(tmp_path: Path) -> None:
    with http_sink(body=b"x" * 64) as (host, port, _seen):
        fixture = build_p142_fixture(tmp_path, authority=f"{host}:{port}", max_response_bytes=8)
        result = process_loopback_transport(fixture.config)
    _emit_counter_marker(result["transport_counters"])
    receipt = read_json(next(fixture.config.receipt_dir.glob("*.json")))
    assert receipt["response_truncated"] is True
    assert receipt["transport_counters"]["loopback_response_byte_count"] == 8


def test_connect_response_body_and_total_timeouts_fail_closed(tmp_path: Path) -> None:
    fixture = build_p142_fixture(tmp_path, authority="127.0.0.1:9", connect_timeout_ms=1, max_attempts=1)
    result = process_loopback_transport(fixture.config, sleep=lambda _seconds: None)
    _emit_counter_marker(result["transport_counters"])
    assert result["transport_counters"]["loopback_transport_failure_count"] == 2


def test_malformed_loopback_response_records_bounded_failure(tmp_path: Path) -> None:
    with http_sink(malformed=True) as (host, port, seen):
        fixture = build_p142_fixture(tmp_path, authority=f"{host}:{port}")
        with pytest.raises(LoopbackTransportError, match="malformed_response"):
            process_loopback_transport(fixture.config)
    _emit_counter_marker(_observed_failure_counters(seen))


def test_dispatch_and_attempt_ids_are_deterministic(tmp_path: Path) -> None:
    fixture = build_p142_fixture(tmp_path)
    envelope = read_json(next(fixture.p141.config.envelope_dir.glob("*.json")))
    route = fixture.config.routes[0]
    body_hash = "sha256:" + "1" * 64
    first = deterministic_dispatch_id(fixture.config.config_hash, envelope["envelope_hash"], route.destination_id, route.route_id, route.method, route.authority, route.path, body_hash)
    assert first == deterministic_dispatch_id(fixture.config.config_hash, envelope["envelope_hash"], route.destination_id, route.route_id, route.method, route.authority, route.path, body_hash)
    assert deterministic_attempt_id(first, 0) != deterministic_attempt_id(first, 1)


def test_completed_replay_is_byte_identical_and_opens_no_socket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with http_sink() as (host, port, _seen):
        fixture = build_p142_fixture(tmp_path, authority=f"{host}:{port}")
        initial = process_loopback_transport(fixture.config)
    before = _tree_bytes(fixture.p142_data)
    monkeypatch.setattr(p142.socket, "socket", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("replayed socket")))
    replay = process_loopback_transport(fixture.config)
    assert replay["dispatch_count"] == 0
    after = {key: value for key, value in _tree_bytes(fixture.p142_data).items() if not str(key).startswith("runs/")}
    before_without_runs = {key: value for key, value in before.items() if not str(key).startswith("runs/")}
    assert after == before_without_runs
    _emit_counter_marker(initial["transport_counters"])


def test_replayed_receipt_must_bind_current_record_journal_and_receipt_hash_before_cursor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with http_sink() as (host, port, _seen):
        fixture = build_p142_fixture(tmp_path, authority=f"{host}:{port}")
        process_loopback_transport(fixture.config)
    envelopes_by_hash = {
        envelope["envelope_hash"]: envelope
        for path in fixture.p141.config.envelope_dir.glob("*.json")
        for envelope in [read_json(path)]
    }
    receipts = [
        (path, read_json(path), envelopes_by_hash[read_json(path)["p141_binding"]["envelope_hash"]])
        for path in fixture.config.receipt_dir.glob("*.json")
    ]
    first_sequence = min(int(envelope["source_event"]["sequence"]) for _path, _receipt, envelope in receipts)
    same_event = sorted(
        (item for item in receipts if int(item[2]["source_event"]["sequence"]) == first_sequence),
        key=lambda item: str(item[2]["destination_id"]),
    )
    target_path, _target_receipt, target_envelope = same_event[0]
    _donor_path, donor_receipt, donor_envelope = same_event[1]
    assert target_envelope["destination_id"] != donor_envelope["destination_id"]
    write_json(target_path, donor_receipt)
    fixture.config.cursor_path.unlink()
    monkeypatch.setattr(p142.socket, "socket", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("receipt accepted after socket")))
    with pytest.raises(LoopbackTransportError, match="receipt_binding_invalid|receipt_journal_hash_invalid"):
        process_loopback_transport(fixture.config)
    if fixture.config.cursor_path.exists():
        assert read_json(fixture.config.cursor_path)["last_sequence"] < first_sequence


def test_refused_retry_attempt_counters_are_aggregated_in_receipts(tmp_path: Path) -> None:
    fixture = build_p142_fixture(tmp_path, authority="127.0.0.1:9", max_attempts=2)
    result = process_loopback_transport(fixture.config, sleep=lambda _seconds: None)
    receipts = [read_json(path) for path in fixture.config.receipt_dir.glob("*.json")]
    assert receipts
    for receipt in receipts:
        assert receipt["transport_counters"]["loopback_socket_attempt_count"] == 2
        assert receipt["transport_counters"]["loopback_transport_failure_count"] == 2
        assert receipt["transport_counters"]["loopback_retry_count"] == 1
    assert result["transport_counters"]["loopback_socket_attempt_count"] == 4
    assert result["transport_counters"]["loopback_transport_failure_count"] == 4
    assert result["transport_counters"]["loopback_retry_count"] == 2


def test_only_pre_socket_connection_failures_advance_to_next_ordinal(tmp_path: Path) -> None:
    fixture = build_p142_fixture(tmp_path, authority="127.0.0.1:9", max_attempts=2)
    result = process_loopback_transport(fixture.config, sleep=lambda _seconds: None)
    _emit_counter_marker(result["transport_counters"])
    journals = [read_json(path) for path in fixture.config.journal_dir.glob("*.json")]
    assert all([entry["attempt_ordinal"] for entry in journal["entries"]] == [0, 1] for journal in journals)
    assert all("connection_failure" in journal["entries"][0] for journal in journals)


def test_complete_http_statuses_never_retry_after_request_commit(tmp_path: Path) -> None:
    results: list[dict[str, int]] = []
    for status in (408, 425, 429, 500):
        with http_sink(status=status) as (host, port, _seen):
            fixture = build_p142_fixture(tmp_path / str(status), authority=f"{host}:{port}", max_attempts=2)
            run = process_loopback_transport(fixture.config)
            results.append(run["transport_counters"])
        journal = read_json(next(fixture.config.journal_dir.glob("*.json")))
        assert len(journal["entries"]) == 1
    _emit_counter_marker(_sum_counter_maps(*results))


def test_retry_after_seconds_is_bounded_advisory_without_post_commit_wait(tmp_path: Path) -> None:
    slept: list[float] = []
    with http_sink(status=429, headers={"Retry-After": "1"}) as (host, port, _seen):
        fixture = build_p142_fixture(tmp_path, authority=f"{host}:{port}")
        result = process_loopback_transport(fixture.config, sleep=slept.append, wall_clock=lambda: datetime(2026, 7, 14, tzinfo=UTC))
    _emit_counter_marker(result["transport_counters"])
    receipt = read_json(next(fixture.config.receipt_dir.glob("*.json")))
    assert receipt["retry_after"] == {"present": True, "valid": True, "delay_ms": 1000, "reason": None}
    assert slept == []


def test_retry_after_imf_fixdate_uses_injected_utc_ceiling_and_monotonic_budget() -> None:
    parsed = parse_retry_after("Wed, 15 Jul 2026 00:00:02 GMT", wall_clock=datetime(2026, 7, 15, 0, 0, 1, 100000, tzinfo=UTC), max_retry_after_ms=5000, remaining_ms=5000)
    assert parsed["delay_ms"] == 1000
    stale = parse_retry_after("Wed, 15 Jul 2026 00:00:00 GMT", wall_clock=datetime(2026, 7, 15, 0, 0, 1, tzinfo=UTC), max_retry_after_ms=5000, remaining_ms=5000)
    assert stale["delay_ms"] == 0


def test_obsolete_ambiguous_non_utc_and_excessive_retry_after_is_rejected() -> None:
    now = datetime(2026, 7, 15, tzinfo=UTC)
    for value in ("Sunday, 06-Nov-94 08:49:37 GMT", "Sun Nov  6 08:49:37 1994", "-1", "Wed, 15 Jul 2026 00:00:01 PST", "999"):
        assert parse_retry_after(value, wall_clock=now, max_retry_after_ms=100, remaining_ms=100)["valid"] is False


def test_attempt_journal_phases_recover_without_replaying_request_committed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = build_p142_fixture(tmp_path)
    envelope = read_json(next(fixture.p141.config.envelope_dir.glob("*.json")))
    route = fixture.config.routes[0]
    body = p142._request_body(envelope, route)
    record = p142._dispatch_record(fixture.config, envelope, route, body)
    fixture.config.journal_dir.mkdir(parents=True, exist_ok=True)
    entry = {"attempt_ordinal": 0, "attempt_id": deterministic_attempt_id(record["dispatch_id"], 0), "phases": ["pre_socket", "request_committed"]}
    p142._write_journal(fixture.config, fixture.config.journal_dir / f"{record['dispatch_id'][7:]}.json", record["dispatch_id"], [entry])
    p142._write_or_validate_dispatch(fixture.config, record)
    monkeypatch.setattr(p142.socket, "socket", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no replay")))
    result = p142._dispatch_or_recover(fixture.config, record, route, body, clock=lambda: 0.0, sleep=lambda _seconds: None, wall_clock=lambda: datetime(2026, 7, 14, tzinfo=UTC))
    assert result["receipt"]["failure_class"] == "request_committed_response_unknown"


def test_contradictory_attempt_after_request_commit_fails_before_socket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = build_p142_fixture(tmp_path)
    envelope = read_json(next(fixture.p141.config.envelope_dir.glob("*.json")))
    route = fixture.config.routes[0]
    body = p142._request_body(envelope, route)
    record = p142._dispatch_record(fixture.config, envelope, route, body)
    fixture.config.journal_dir.mkdir(parents=True, exist_ok=True)
    entries = [
        {
            "attempt_ordinal": 0,
            "attempt_id": deterministic_attempt_id(record["dispatch_id"], 0),
            "phases": ["pre_socket", "request_committed"],
        },
        {
            "attempt_ordinal": 1,
            "attempt_id": deterministic_attempt_id(record["dispatch_id"], 1),
            "phases": ["pre_socket"],
            "connection_failure": {"class": "ConnectionRefusedError"},
        },
    ]
    journal = {
        "schema_version": p142.JOURNAL_SCHEMA_VERSION,
        "dispatch_id": record["dispatch_id"],
        "config_hash": fixture.config.config_hash,
        "entries": entries,
    }
    journal["journal_hash"] = stable_hash(journal)
    write_json(fixture.config.journal_dir / f"{record['dispatch_id'][7:]}.json", journal)
    p142._write_or_validate_dispatch(fixture.config, record)
    socket_calls = 0

    def forbidden_socket(*_args: object, **_kwargs: object) -> None:
        nonlocal socket_calls
        socket_calls += 1
        raise AssertionError("contradictory journal must not open a socket")

    monkeypatch.setattr(p142.socket, "socket", forbidden_socket)
    with pytest.raises(LoopbackTransportError, match="journal_terminal_attempt_not_last"):
        p142._dispatch_or_recover(
            fixture.config,
            record,
            route,
            body,
            clock=lambda: 0.0,
            sleep=lambda _seconds: None,
            wall_clock=lambda: datetime(2026, 7, 14, tzinfo=UTC),
        )
    assert socket_calls == 0


def test_loopback_transport_lease_conflict_fails_before_dispatch(tmp_path: Path) -> None:
    fixture = build_p142_fixture(tmp_path)
    fixture.config.lease_path.parent.mkdir(parents=True, exist_ok=True)
    with p142._LoopbackLease(fixture.config):
        with pytest.raises(LoopbackTransportError, match="lease_unavailable"):
            process_loopback_transport(fixture.config)


def test_cursor_advances_only_after_all_receipts_are_durable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with http_sink() as (host, port, seen):
        fixture = build_p142_fixture(tmp_path, authority=f"{host}:{port}")
        original = p142._atomic_write_json

        def fail_receipt(path: Path, value: object, roots: object) -> None:
            if path.parent == fixture.config.receipt_dir:
                raise OSError("receipt crash")
            original(path, value, roots)  # type: ignore[arg-type]

        monkeypatch.setattr(p142, "_atomic_write_json", fail_receipt)
        with pytest.raises(OSError, match="receipt crash"):
            process_loopback_transport(fixture.config)
    assert not fixture.config.cursor_path.exists()
    counters = _observed_failure_counters(seen)
    counters["loopback_transport_failure_count"] = 0
    counters["loopback_complete_response_count"] = len(seen)
    counters["loopback_response_byte_count"] = len(b"ok") * len(seen)
    counters["loopback_http_2xx_count"] = len(seen)
    _emit_counter_marker(counters)


def test_same_event_destinations_recover_as_one_cursor_batch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with http_sink() as (host, port, seen):
        fixture = build_p142_fixture(tmp_path, authority=f"{host}:{port}")
        envelopes = p142._validated_p141_envelopes(fixture.config)
        first_batch = p142._event_envelope_batches(envelopes)[0]
        assert len(first_batch) >= 2
        batch_sequence = int(first_batch[0]["source_event"]["sequence"])
        original_dispatch = p142._dispatch_or_recover
        calls = 0

        def crash_before_second_destination(
            config: p142.LoopbackTransportConfig,
            record: Mapping[str, Any],
            route: p142.LoopbackRoute,
            request_body: bytes,
            *,
            clock: Callable[[], float],
            sleep: Callable[[float], None],
            wall_clock: Callable[[], datetime],
        ) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("second destination crash")
            return original_dispatch(
                config,
                record,
                route,
                request_body,
                clock=clock,
                sleep=sleep,
                wall_clock=wall_clock,
            )

        monkeypatch.setattr(p142, "_dispatch_or_recover", crash_before_second_destination)
        with pytest.raises(OSError, match="second destination crash"):
            process_loopback_transport(fixture.config)
        assert len(list(fixture.config.receipt_dir.glob("*.json"))) == 1
        if fixture.config.cursor_path.exists():
            assert read_json(fixture.config.cursor_path)["last_sequence"] < batch_sequence

        monkeypatch.setattr(p142, "_dispatch_or_recover", original_dispatch)
        restarted = process_loopback_transport(fixture.config)

    assert restarted["replayed_dispatch_count"] >= 1
    assert read_json(fixture.config.cursor_path)["last_sequence"] >= batch_sequence
    assert len(seen) >= 2


def test_durable_receipt_before_journal_mark_recovers_without_socket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with http_sink() as (host, port, _seen):
        fixture = build_p142_fixture(tmp_path, authority=f"{host}:{port}")
        envelope = read_json(next(fixture.p141.config.envelope_dir.glob("*.json")))
        route = fixture.config.routes[0]
        body = p142._request_body(envelope, route)
        record = p142._dispatch_record(fixture.config, envelope, route, body)
        p142._ensure_output_dirs(fixture.config)
        p142._write_or_validate_dispatch(fixture.config, record)
        original_write_journal = p142._write_journal

        def crash_before_journal_mark(
            config: p142.LoopbackTransportConfig,
            path: Path,
            dispatch_id: str,
            entries: Sequence[Mapping[str, Any]],
        ) -> dict[str, Any]:
            attempt_entries = list(entries)
            if attempt_entries[-1]["phases"][-1] == "receipt_written":
                raise OSError("journal mark crash")
            return original_write_journal(config, path, dispatch_id, attempt_entries)

        monkeypatch.setattr(p142, "_write_journal", crash_before_journal_mark)
        with pytest.raises(OSError, match="journal mark crash"):
            p142._dispatch_or_recover(
                fixture.config,
                record,
                route,
                body,
                clock=lambda: 0.0,
                sleep=lambda _seconds: None,
                wall_clock=lambda: datetime(2026, 7, 14, tzinfo=UTC),
            )

    receipt_path = fixture.config.receipt_dir / f"{record['dispatch_id'][7:]}.json"
    journal_path = fixture.config.journal_dir / f"{record['dispatch_id'][7:]}.json"
    receipt_before = receipt_path.read_bytes()
    journal_before = read_json(journal_path)
    assert journal_before["entries"][-1]["phases"][-1] == "complete_response_observed"
    assert "receipt_hash" not in journal_before["entries"][-1]
    monkeypatch.setattr(p142, "_write_journal", original_write_journal)
    socket_calls = 0

    def forbidden_socket(*_args: object, **_kwargs: object) -> None:
        nonlocal socket_calls
        socket_calls += 1
        raise AssertionError("receipt recovery must not open a socket")

    monkeypatch.setattr(p142.socket, "socket", forbidden_socket)
    recovered = p142._dispatch_or_recover(
        fixture.config,
        record,
        route,
        body,
        clock=lambda: 0.0,
        sleep=lambda _seconds: None,
        wall_clock=lambda: datetime(2026, 7, 14, tzinfo=UTC),
    )
    journal_after = read_json(journal_path)
    assert recovered["replayed"] is True
    assert receipt_path.read_bytes() == receipt_before
    assert journal_after["entries"][-1]["phases"][-1] == "receipt_written"
    assert journal_after["entries"][-1]["receipt_hash"] == recovered["receipt"]["receipt_hash"]
    assert socket_calls == 0


@pytest.mark.parametrize("terminal_kind", ["response_unknown", "connection_failure"])
def test_all_terminal_receipts_recover_after_receipt_write_before_journal_mark_without_socket(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    terminal_kind: str,
) -> None:
    fixture = build_p142_fixture(tmp_path / terminal_kind)
    envelope = read_json(next(fixture.p141.config.envelope_dir.glob("*.json")))
    route = fixture.config.routes[0]
    body = p142._request_body(envelope, route)
    record = p142._dispatch_record(fixture.config, envelope, route, body)
    p142._ensure_output_dirs(fixture.config)
    p142._write_or_validate_dispatch(fixture.config, record)
    entry: dict[str, Any] = {
        "attempt_ordinal": 0,
        "attempt_id": deterministic_attempt_id(str(record["dispatch_id"]), 0),
        "phases": ["pre_socket", "request_committed"],
    }
    if terminal_kind == "connection_failure":
        entry["phases"] = ["pre_socket"]
        entry["connection_failure"] = {"class": "ConnectionRefusedError"}
    journal_path = fixture.config.journal_dir / f"{str(record['dispatch_id'])[7:]}.json"
    receipt_path = fixture.config.receipt_dir / f"{str(record['dispatch_id'])[7:]}.json"
    journal = p142._write_journal(fixture.config, journal_path, str(record["dispatch_id"]), [entry])
    if terminal_kind == "response_unknown":
        receipt = p142._receipt_from_unknown(fixture.config, record, journal["entries"])
    else:
        counters = p142.zero_transport_counters()
        counters["loopback_socket_attempt_count"] = 1
        counters["loopback_transport_failure_count"] = 1
        receipt = p142._receipt_from_failure(
            fixture.config,
            record,
            journal["entries"],
            "connection_failed",
            counters,
        )
    original_mark = p142._mark_receipt_written

    def crash_before_mark(*_args: object, **_kwargs: object) -> dict[str, Any]:
        raise OSError("terminal journal mark crash")

    monkeypatch.setattr(p142, "_mark_receipt_written", crash_before_mark)
    with pytest.raises(OSError, match="terminal journal mark crash"):
        p142._write_receipt_and_mark(fixture.config, journal_path, journal, receipt_path, receipt)
    receipt_before = receipt_path.read_bytes()
    pending_journal = read_json(journal_path)
    assert "receipt_intent" in pending_journal["entries"][-1]
    assert "receipt_hash" not in pending_journal["entries"][-1]

    monkeypatch.setattr(p142, "_mark_receipt_written", original_mark)
    socket_calls = 0

    def forbidden_socket(*_args: object, **_kwargs: object) -> None:
        nonlocal socket_calls
        socket_calls += 1
        raise AssertionError("terminal receipt recovery must not open a socket")

    monkeypatch.setattr(p142.socket, "socket", forbidden_socket)
    recovered = p142._dispatch_or_recover(
        fixture.config,
        record,
        route,
        body,
        clock=lambda: 0.0,
        sleep=lambda _seconds: None,
        wall_clock=lambda: datetime(2026, 7, 14, tzinfo=UTC),
    )
    final_journal = read_json(journal_path)
    assert recovered["replayed"] is True
    assert receipt_path.read_bytes() == receipt_before
    assert final_journal["entries"][-1]["receipt_hash"] == receipt["receipt_hash"]
    assert socket_calls == 0


def test_receipt_intent_recovers_crash_before_receipt_write_without_socket(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_p142_fixture(tmp_path)
    envelope = read_json(next(fixture.p141.config.envelope_dir.glob("*.json")))
    route = fixture.config.routes[0]
    body = p142._request_body(envelope, route)
    record = p142._dispatch_record(fixture.config, envelope, route, body)
    p142._ensure_output_dirs(fixture.config)
    p142._write_or_validate_dispatch(fixture.config, record)
    entry = {
        "attempt_ordinal": 0,
        "attempt_id": deterministic_attempt_id(str(record["dispatch_id"]), 0),
        "phases": ["pre_socket"],
        "connection_failure": {"class": "ConnectionRefusedError"},
    }
    journal_path = fixture.config.journal_dir / f"{str(record['dispatch_id'])[7:]}.json"
    receipt_path = fixture.config.receipt_dir / f"{str(record['dispatch_id'])[7:]}.json"
    journal = p142._write_journal(fixture.config, journal_path, str(record["dispatch_id"]), [entry])
    counters = p142.zero_transport_counters()
    counters["loopback_socket_attempt_count"] = 1
    counters["loopback_transport_failure_count"] = 1
    receipt = p142._receipt_from_failure(
        fixture.config,
        record,
        journal["entries"],
        "connection_failed",
        counters,
    )
    original_atomic = p142._atomic_write_json

    def crash_before_receipt(path: Path, value: object, roots: Sequence[Path]) -> None:
        if path == receipt_path:
            raise OSError("receipt write crash")
        original_atomic(path, value, roots)

    monkeypatch.setattr(p142, "_atomic_write_json", crash_before_receipt)
    with pytest.raises(OSError, match="receipt write crash"):
        p142._write_receipt_and_mark(fixture.config, journal_path, journal, receipt_path, receipt)
    assert not receipt_path.exists()
    assert "receipt_intent" in read_json(journal_path)["entries"][-1]

    monkeypatch.setattr(p142, "_atomic_write_json", original_atomic)
    socket_calls = 0

    def forbidden_socket(*_args: object, **_kwargs: object) -> None:
        nonlocal socket_calls
        socket_calls += 1
        raise AssertionError("receipt-intent recovery must not open a socket")

    monkeypatch.setattr(p142.socket, "socket", forbidden_socket)
    recovered = p142._dispatch_or_recover(
        fixture.config,
        record,
        route,
        body,
        clock=lambda: 0.0,
        sleep=lambda _seconds: None,
        wall_clock=lambda: datetime(2026, 7, 14, tzinfo=UTC),
    )
    assert recovered["replayed"] is True
    assert read_json(receipt_path) == receipt
    assert read_json(journal_path)["entries"][-1]["receipt_hash"] == receipt["receipt_hash"]
    assert socket_calls == 0


def test_receipt_intent_requires_proven_terminal_journal_state(tmp_path: Path) -> None:
    fixture = build_p142_fixture(tmp_path)
    envelope = read_json(next(fixture.p141.config.envelope_dir.glob("*.json")))
    route = fixture.config.routes[0]
    body = p142._request_body(envelope, route)
    record = p142._dispatch_record(fixture.config, envelope, route, body)
    p142._ensure_output_dirs(fixture.config)
    entry: dict[str, Any] = {
        "attempt_ordinal": 0,
        "attempt_id": deterministic_attempt_id(str(record["dispatch_id"]), 0),
        "phases": ["pre_socket"],
    }
    counters = p142.zero_transport_counters()
    counters["loopback_transport_failure_count"] = 1
    receipt = p142._receipt_from_failure(
        fixture.config,
        record,
        [entry],
        "connection_failed",
        counters,
    )
    entry["receipt_intent"] = {
        "receipt": receipt,
        "receipt_bytes_sha256": "sha256:" + hashlib.sha256(p142._json_bytes(receipt)).hexdigest(),
    }
    journal_path = fixture.config.journal_dir / f"{str(record['dispatch_id'])[7:]}.json"
    with pytest.raises(LoopbackTransportError, match="receipt_intent_terminal_state_invalid"):
        p142._write_journal(fixture.config, journal_path, str(record["dispatch_id"]), [entry])
    assert not journal_path.exists()


def test_artifact_count_total_bytes_and_free_space_fail_before_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = build_p142_fixture(tmp_path, max_artifact_files=1)
    with pytest.raises(LoopbackTransportError, match="artifact_budget_exhausted"):
        process_loopback_transport(fixture.config)
    no_space = build_p142_fixture(tmp_path / "space")
    disk_usage_result = type("DiskUsage", (), {"total": 100, "used": 100, "free": 0})()
    monkeypatch.setattr(p142.shutil, "disk_usage", lambda _path: disk_usage_result)
    with pytest.raises(LoopbackTransportError, match="insufficient_artifact_space"):
        process_loopback_transport(no_space.config)


def test_temp_write_fsync_replace_and_directory_fsync_failures_preserve_prior_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = build_p142_fixture(tmp_path)
    target = fixture.config.cursor_path
    target.parent.mkdir(parents=True, exist_ok=True)
    original = p142.os.replace
    target.write_text('{"prior":true}\n', encoding="utf-8")
    before = target.read_bytes()
    monkeypatch.setattr(p142.os, "replace", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("replace failed")))
    with pytest.raises(OSError, match="replace failed"):
        p142._atomic_write_json(target, {"next": True}, fixture.config.writable_roots)
    monkeypatch.setattr(p142.os, "replace", original)
    assert target.read_bytes() == before


def test_no_p133_ack_and_no_p141_mutation_authority(tmp_path: Path) -> None:
    with http_sink() as (host, port, _seen):
        fixture = build_p142_fixture(tmp_path, authority=f"{host}:{port}")
        before = _tree_bytes(fixture.p141.p133_data) | {Path("p141") / key: value for key, value in _tree_bytes(fixture.p141.p141_data).items()}
        result = process_loopback_transport(fixture.config)
        after = _tree_bytes(fixture.p141.p133_data) | {Path("p141") / key: value for key, value in _tree_bytes(fixture.p141.p141_data).items()}
    assert result["authority_counters"]["p133_ack_write_count"] == 0
    assert after == before
    _emit_counter_marker(result["transport_counters"])


def test_action_remediation_and_mutation_entrypoints_are_never_called(tmp_path: Path) -> None:
    with http_sink() as (host, port, _seen):
        fixture = build_p142_fixture(tmp_path, authority=f"{host}:{port}")
        result = process_loopback_transport(fixture.config)
    _emit_counter_marker(result["transport_counters"])
    for key in ("action_execution_count", "remediation_execution_count", "staging_mutation_count", "production_mutation_count"):
        assert result["authority_counters"][key] == 0


def test_runtime_source_and_valid_paths_do_not_use_commands_or_subprocesses(tmp_path: Path) -> None:
    source = Path(p142.__file__).read_text(encoding="utf-8")
    assert "subprocess." not in source
    assert "getaddrinfo" not in source
    assert "create_connection" not in source
    assert "HTTPConnection" not in source
    with http_sink() as (host, port, _seen):
        fixture = build_p142_fixture(tmp_path, authority=f"{host}:{port}")
        result = process_loopback_transport(fixture.config)
    _emit_counter_marker(result["transport_counters"])
    assert result["authority_counters"]["subprocess_shell_count"] == 0
    assert result["authority_counters"]["arbitrary_command_execution_count"] == 0


def _tree_bytes(root: Path) -> dict[Path, bytes]:
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file() and not path.name.endswith(".lock")}
