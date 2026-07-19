from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import urlencode

STARTED_AT = time.time()
RECEIPT_DIR = Path(os.environ.get("RECEIPT_DIR", "/var/lib/p174-observer"))
CHAIN_STATE_PATH = "chain-state.json"
RECEIPTS_PATH = "receipts.jsonl"
EVALUATIONS_PATH = "evaluations.jsonl"
REQUIRED_SOURCES = ("prometheus", "loki", "api")
MAX_RECEIPT_AGE_SECONDS = int(os.environ.get("MAX_RECEIPT_AGE_SECONDS", "60"))
CHAIN_LOCK = RLock()
READS_TOTAL = 0
READ_ERRORS_TOTAL = 0
SUCCESSFUL_EVIDENCE_TOTAL = 0


def redact_url(url: str) -> str:
    return url.split("?", 1)[0]


def canonical_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def session_binding() -> dict[str, str]:
    session_id = os.environ.get("P174_SESSION_ID", "").strip()
    manifest_sha256 = os.environ.get("P174_MANIFEST_SHA256", "").strip()
    if not session_id:
        raise ValueError("missing_session_id")
    if len(manifest_sha256) != 64 or any(char not in "0123456789abcdef" for char in manifest_sha256):
        raise ValueError("missing_or_invalid_manifest_sha256")
    return {"session_id": session_id, "manifest_sha256": manifest_sha256}


def health_signal(name: str, status: int, body: bytes) -> tuple[bool, str]:
    if status != 200:
        return False, "status_not_200"
    text = body.decode("utf-8", errors="replace").lower()
    if name == "prometheus":
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return False, "prometheus_invalid_json"
        results = payload.get("data", {}).get("result", [])
        up_values = [str(item.get("value", ["", "0"])[1]) for item in results if isinstance(item, dict)]
        if payload.get("status") == "success" and up_values and all(value == "1" for value in up_values):
            return True, "prometheus_up"
        return False, "prometheus_up_missing_or_down"
    if name == "loki":
        if "ready" in text:
            return True, "loki_ready"
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return False, "loki_invalid_json"
        results = payload.get("data", {}).get("result", []) if isinstance(payload, dict) else []
        if payload.get("status") == "success" and isinstance(results, list) and results:
            return True, "loki_log_stream_observed"
        return False, "loki_log_stream_missing"
    if name == "api":
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("metrics"), dict):
            metrics = payload["metrics"]
            service_up = float(metrics.get("service_up", 0)) >= 1
            error_rate = float(metrics.get("error_rate", 1))
            latency_ms = float(metrics.get("latency_ms", 1_000_000))
            queue_depth = float(metrics.get("queue_depth", 1_000_000))
            pool_size = max(1.0, float(metrics.get("pool_size", 1)))
            if service_up and error_rate <= 0.10 and latency_ms <= 1_000 and queue_depth <= max(20.0, pool_size * 4):
                return True, "api_operational_metrics_healthy"
            return False, "api_operational_metrics_unhealthy"
        if any(token in text for token in ("healthy", '"ok"', ": true")):
            return True, "api_health_body_ok"
        return False, "api_health_body_unrecognized"
    return False, "unknown_source"


def receipt_for(name: str, url: str, status: int, body: bytes) -> dict[str, object]:
    healthy, reason = health_signal(name, status, body)
    return {
        "schema_version": "p174.telemetry_receipt.v1",
        "collected_at": time.time(),
        **session_binding(),
        "source": name,
        "url": redact_url(url),
        "status": status,
        "evidence_success": healthy,
        "health_reason": reason,
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "body_bytes": len(body),
    }


def append_receipt(payload: dict[str, object]) -> None:
    with CHAIN_LOCK:
        RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
        state_path = RECEIPT_DIR / CHAIN_STATE_PATH
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
        else:
            state = {"last_sequence": 0, "last_receipt_hash": None}
        chained = {
            **payload,
            "sequence": int(state["last_sequence"]) + 1,
            "previous_receipt_hash": state["last_receipt_hash"],
        }
        chained["receipt_hash"] = canonical_hash(chained)
        with (RECEIPT_DIR / RECEIPTS_PATH).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(chained, sort_keys=True) + "\n")
        state_path.write_text(
            json.dumps({"last_sequence": chained["sequence"], "last_receipt_hash": chained["receipt_hash"]}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        payload.clear()
        payload.update(chained)


def validate_receipt_chain(
    receipts: list[dict[str, object]],
    *,
    expected_previous_hash: str | None = None,
    expected_first_sequence: int | None = None,
) -> list[str]:
    failures: list[str] = []
    previous_hash: str | None = None
    previous_sequence: int | None = None
    for receipt in receipts:
        candidate = dict(receipt)
        receipt_hash = candidate.pop("receipt_hash", None)
        sequence = candidate.get("sequence")
        if not isinstance(sequence, int):
            failures.append(f"invalid_sequence:{receipt.get('source')}")
        elif previous_sequence is not None and sequence != previous_sequence + 1:
            failures.append(f"sequence_gap:{receipt.get('source')}")
        if previous_hash is not None and candidate.get("previous_receipt_hash") != previous_hash:
            failures.append(f"previous_hash_mismatch:{receipt.get('source')}")
        expected = canonical_hash(candidate)
        if receipt_hash != expected:
            failures.append(f"receipt_hash_mismatch:{receipt.get('source')}")
        previous_hash = str(receipt_hash) if receipt_hash else None
        previous_sequence = sequence if isinstance(sequence, int) else None
    if receipts and receipts[0].get("previous_receipt_hash") != expected_previous_hash:
        failures.append("batch_previous_hash_mismatch")
    if receipts and expected_first_sequence is not None and receipts[0].get("sequence") != expected_first_sequence:
        failures.append("batch_first_sequence_mismatch")
    return failures


def evaluate_receipts(
    receipts: list[dict[str, object]],
    *,
    now: float | None = None,
    expected_previous_hash: str | None = None,
    expected_first_sequence: int | None = None,
) -> dict[str, object]:
    now = time.time() if now is None else now
    failures: list[str] = []
    by_source: dict[str, dict[str, object]] = {}
    for receipt in receipts:
        source = receipt.get("source")
        if not isinstance(source, str):
            failures.append("missing_source")
            continue
        if source in by_source:
            failures.append(f"duplicate_source:{source}")
            continue
        by_source[source] = receipt
    for source in REQUIRED_SOURCES:
        current = by_source.get(source)
        if current is None:
            failures.append(f"missing_source:{source}")
            continue
        if current.get("status") != 200:
            failures.append(f"bad_status:{source}")
        collected_at = current.get("collected_at")
        if not isinstance(collected_at, int | float) or now - float(collected_at) > MAX_RECEIPT_AGE_SECONDS or collected_at > now + 5:
            failures.append(f"stale_or_invalid_freshness:{source}")
        if not current.get("session_id") or not current.get("manifest_sha256"):
            failures.append(f"missing_binding:{source}")
        if current.get("evidence_success") is not True:
            failures.append(f"health_signal_failed:{source}")
    failures.extend(
        validate_receipt_chain(
            receipts,
            expected_previous_hash=expected_previous_hash,
            expected_first_sequence=expected_first_sequence,
        )
    )
    signals = {source: bool(by_source.get(source, {}).get("evidence_success")) and by_source.get(source, {}).get("status") == 200 for source in REQUIRED_SOURCES}
    score = sum(1 for passed in signals.values() if passed) / len(REQUIRED_SOURCES)
    return {
        "schema_version": "p174.telemetry_evaluation.v1",
        "ts": now,
        "healthy": not failures,
        "score": score,
        "signals": signals,
        "failures": failures,
    }


def fetch(name: str, url: str) -> dict[str, object]:
    global READS_TOTAL, READ_ERRORS_TOTAL, SUCCESSFUL_EVIDENCE_TOTAL
    READS_TOTAL += 1
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            body = response.read(4096)
            payload = receipt_for(name, url, int(response.status), body)
    except (OSError, urllib.error.URLError) as exc:
        payload = receipt_for(name, url, 0, str(exc).encode("utf-8"))
        READ_ERRORS_TOTAL += 1
    append_receipt(payload)
    if payload.get("evidence_success") is True:
        SUCCESSFUL_EVIDENCE_TOTAL += 1
    return payload


def write_json(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, object]) -> None:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class ObserverHandler(BaseHTTPRequestHandler):
    server_version = "opscat-p174-observer"

    def do_GET(self) -> None:
        if self.path == "/health":
            write_json(
                self,
                200,
                {
                    "uptime_seconds": round(time.time() - STARTED_AT, 3),
                    "reads_total": READS_TOTAL,
                    "read_errors_total": READ_ERRORS_TOTAL,
                    "successful_evidence_total": SUCCESSFUL_EVIDENCE_TOTAL,
                },
            )
            return
        if self.path == "/metrics":
            body = "\n".join(
                [
                    "# HELP p174_observer_reads_total Observer evidence read attempts.",
                    "# TYPE p174_observer_reads_total counter",
                    f"p174_observer_reads_total {READS_TOTAL}",
                    "# HELP p174_observer_read_errors_total Observer evidence read errors.",
                    "# TYPE p174_observer_read_errors_total counter",
                    f"p174_observer_read_errors_total {READ_ERRORS_TOTAL}",
                    "# HELP p174_observer_successful_evidence_total Observer successful independent evidence reads.",
                    "# TYPE p174_observer_successful_evidence_total counter",
                    f"p174_observer_successful_evidence_total {SUCCESSFUL_EVIDENCE_TOTAL}",
                    "",
                ]
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "text/plain; version=0.0.4")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/collect":
            try:
                sources = {
                    "prometheus": os.environ.get("TARGET_PROMETHEUS_URL", "").rstrip("/") + "/api/v1/query?query=up",
                    "loki": os.environ.get("TARGET_LOKI_URL", "").rstrip("/") + "/loki/api/v1/query?" + urlencode({"query": '{job="p174-docker-containers"}', "limit": "1"}),
                    "api": os.environ.get("TARGET_API_URL", "").rstrip("/") + "/state",
                }
                with CHAIN_LOCK:
                    state_path = RECEIPT_DIR / CHAIN_STATE_PATH
                    chain_state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"last_sequence": 0, "last_receipt_hash": None}
                    last_sequence = chain_state.get("last_sequence")
                    last_receipt_hash = chain_state.get("last_receipt_hash")
                    if not isinstance(last_sequence, int) or not isinstance(last_receipt_hash, str | None):
                        raise ValueError("chain_state_invalid")
                    receipts = [fetch(name, url) for name, url in sources.items()]
                    evaluation = evaluate_receipts(
                        receipts,
                        expected_previous_hash=last_receipt_hash,
                        expected_first_sequence=last_sequence + 1,
                    )
                write_json(self, 200, {"receipts": receipts, "evaluation": evaluation})
            except ValueError as exc:
                write_json(self, 500, {"error": str(exc)})
            return
        write_json(self, 404, {"error": "not_found"})

    def log_message(self, fmt: str, *args: object) -> None:
        print(json.dumps({"ts": time.time(), "component": self.server_version, "message": fmt % args}), flush=True)


def run_observer() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 8030), ObserverHandler)
    print(json.dumps({"ts": time.time(), "event": "started", "role": "observer", "port": 8030}), flush=True)
    server.serve_forever()


def record_failed_evaluation(exc: Exception) -> None:
    healthy_path = Path("/tmp/evaluator.healthy")
    if healthy_path.exists():
        healthy_path.unlink()
    failed = {
        "schema_version": "p174.telemetry_evaluation.v1",
        "ts": time.time(),
        "healthy": False,
        "score": 0.0,
        "signals": {source: False for source in REQUIRED_SOURCES},
        "failures": [f"collection_error:{type(exc).__name__}"],
    }
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    with (RECEIPT_DIR / EVALUATIONS_PATH).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(failed, sort_keys=True) + "\n")
    print(json.dumps({"ts": time.time(), "event": "evaluation_failed_closed", "error_type": type(exc).__name__}), flush=True)


def run_evaluator() -> None:
    url = os.environ.get("OBSERVER_URL", "http://observer:8030").rstrip("/") + "/collect"
    while True:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            evaluation = payload.get("evaluation")
            if not isinstance(evaluation, dict):
                raise ValueError("observer_evaluation_missing")
            RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
            with (RECEIPT_DIR / EVALUATIONS_PATH).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(evaluation, sort_keys=True) + "\n")
            healthy_path = Path("/tmp/evaluator.healthy")
            if evaluation["healthy"]:
                healthy_path.write_text(str(time.time()), encoding="utf-8")
            elif healthy_path.exists():
                healthy_path.unlink()
        except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
            record_failed_evaluation(exc)
        time.sleep(15)


def main() -> None:
    role = os.environ.get("P174_ROLE", "observer")
    if role == "observer":
        run_observer()
    if role == "evaluator":
        run_evaluator()
    raise SystemExit(f"unknown P174_ROLE: {role}")


if __name__ == "__main__":
    main()
