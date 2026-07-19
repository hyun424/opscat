from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
OBSERVER_PATH = ROOT / "lab" / "p174" / "observer" / "p174_observer.py"
COMPOSE_PATH = ROOT / "lab" / "p174" / "docker-compose.observer.yml"
MANIFEST_SHA256 = "a" * 64


def _observer_module() -> Any:
    spec = importlib.util.spec_from_file_location("p174_observer_under_test", OBSERVER_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _healthy_receipts(observer: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    monkeypatch.setenv("P174_SESSION_ID", "session-174")
    monkeypatch.setenv("P174_MANIFEST_SHA256", MANIFEST_SHA256)
    observer.RECEIPT_DIR = tmp_path
    receipts = [
        observer.receipt_for("prometheus", "http://prometheus/api/v1/query?query=up", 200, b'{"status":"success","data":{"result":[{"value":[1,"1"]}]}}'),
        observer.receipt_for("loki", "http://loki/ready", 200, b"ready\n"),
        observer.receipt_for("api", "http://api/health", 200, b'{"status":"healthy"}'),
    ]
    for receipt in receipts:
        observer.append_receipt(receipt)
    return receipts


def test_receipts_are_hash_chained_and_bound_to_session_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    observer = _observer_module()
    receipts = _healthy_receipts(observer, tmp_path, monkeypatch)

    assert [receipt["sequence"] for receipt in receipts] == [1, 2, 3]
    assert receipts[0]["previous_receipt_hash"] is None
    assert receipts[1]["previous_receipt_hash"] == receipts[0]["receipt_hash"]
    assert receipts[2]["previous_receipt_hash"] == receipts[1]["receipt_hash"]
    assert {receipt["session_id"] for receipt in receipts} == {"session-174"}
    assert {receipt["manifest_sha256"] for receipt in receipts} == {MANIFEST_SHA256}
    assert all(receipt["evidence_success"] is True for receipt in receipts)

    evaluation = observer.evaluate_receipts(receipts, now=max(float(cast(float, receipt["collected_at"])) for receipt in receipts))
    assert evaluation["healthy"] is True
    assert evaluation["score"] == 1
    assert evaluation["failures"] == []


def test_evaluator_fails_closed_on_bad_status_even_with_three_receipts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    observer = _observer_module()
    receipts = _healthy_receipts(observer, tmp_path, monkeypatch)
    receipts[-1] = observer.receipt_for("api", "http://api/health", 500, b"error")
    observer.append_receipt(receipts[-1])

    evaluation = observer.evaluate_receipts(receipts, now=max(float(cast(float, receipt["collected_at"])) for receipt in receipts))
    assert evaluation["healthy"] is False
    assert evaluation["score"] == pytest.approx(2 / 3)
    assert "bad_status:api" in evaluation["failures"]
    assert "health_signal_failed:api" in evaluation["failures"]


def test_evaluator_rejects_transport_healthy_but_operationally_overloaded_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    observer = _observer_module()
    receipts = _healthy_receipts(observer, tmp_path, monkeypatch)
    overloaded = b'{"status":"ok","metrics":{"service_up":1,"error_rate":0.98,"latency_ms":3200,"queue_depth":2500,"pool_size":16}}'
    receipts[-1] = observer.receipt_for("api", "http://api/state", 200, overloaded)
    observer.append_receipt(receipts[-1])

    evaluation = observer.evaluate_receipts(receipts, now=max(float(cast(float, receipt["collected_at"])) for receipt in receipts))
    assert evaluation["healthy"] is False
    assert receipts[-1]["health_reason"] == "api_operational_metrics_unhealthy"
    assert "health_signal_failed:api" in evaluation["failures"]


def test_evaluator_fails_closed_on_missing_source_and_stale_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    observer = _observer_module()
    receipts = _healthy_receipts(observer, tmp_path, monkeypatch)
    receipts = receipts[:2]
    receipts[0]["collected_at"] = 1.0
    receipts[0]["receipt_hash"] = observer.canonical_hash({key: value for key, value in receipts[0].items() if key != "receipt_hash"})

    evaluation = observer.evaluate_receipts(receipts, now=1_000.0)
    assert evaluation["healthy"] is False
    assert "missing_source:api" in evaluation["failures"]
    assert "stale_or_invalid_freshness:prometheus" in evaluation["failures"]


def test_receipt_batch_requires_exact_prior_tip_and_first_sequence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    observer = _observer_module()
    receipts = _healthy_receipts(observer, tmp_path, monkeypatch)

    valid = observer.evaluate_receipts(receipts, expected_previous_hash=None, expected_first_sequence=1)
    wrong_tip = observer.evaluate_receipts(receipts, expected_previous_hash="forged", expected_first_sequence=1)
    wrong_sequence = observer.evaluate_receipts(receipts, expected_previous_hash=None, expected_first_sequence=99)

    assert valid["healthy"] is True
    assert "batch_previous_hash_mismatch" in wrong_tip["failures"]
    assert "batch_first_sequence_mismatch" in wrong_sequence["failures"]


def test_loki_requires_a_real_log_stream_not_only_http_success() -> None:
    observer = _observer_module()
    observed = b'{"status":"success","data":{"resultType":"streams","result":[{"stream":{"job":"p174-docker-containers"},"values":[["1","line"]]}]}}'
    empty = b'{"status":"success","data":{"resultType":"streams","result":[]}}'

    assert observer.health_signal("loki", 200, observed) == (True, "loki_log_stream_observed")
    assert observer.health_signal("loki", 200, empty) == (False, "loki_log_stream_missing")


def test_observer_compose_persists_receipts_to_named_volume_and_requires_binding() -> None:
    compose = COMPOSE_PATH.read_text(encoding="utf-8")
    assert "p174_observer_receipts:" in compose
    assert "p174_observer_receipts:/var/lib/p174-observer" in compose
    assert "P174_SESSION_ID: ${P174_SESSION_ID:-}" in compose
    assert "P174_MANIFEST_SHA256: ${P174_MANIFEST_SHA256:-}" in compose
    assert "RECEIPT_DIR: /var/lib/p174-observer" in compose


def test_evaluator_exception_removes_health_and_records_failure(tmp_path: Path) -> None:
    observer = _observer_module()
    observer.RECEIPT_DIR = tmp_path
    marker = Path("/tmp/evaluator.healthy")
    marker.write_text("stale", encoding="utf-8")

    observer.record_failed_evaluation(ValueError("broken"))

    assert not marker.exists()
    evaluation = observer.json.loads((tmp_path / observer.EVALUATIONS_PATH).read_text(encoding="utf-8"))
    assert evaluation["healthy"] is False
    assert evaluation["failures"] == ["collection_error:ValueError"]
