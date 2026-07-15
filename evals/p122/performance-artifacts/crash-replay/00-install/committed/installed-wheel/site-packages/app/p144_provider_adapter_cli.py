"""CLI for P144 numeric-loopback provider adapter artifacts."""

from __future__ import annotations

import argparse
import socket
import sys
from pathlib import Path
from typing import Any

from app.services.p144_provider_adapter_lab import (
    canonical_json,
    issue_receiver_capability,
    load_adapter_config,
    process_adapter_deliveries,
    zero_forbidden_counters,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the P144 local numeric-loopback provider adapter lab.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    config = load_adapter_config(args.config)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    capability = issue_receiver_capability(listener)

    # The CLI fixture receiver returns a deterministic accepted response for
    # each local connection; it is numeric-loopback only and uses no provider SDK.
    import threading

    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                conn, _addr = listener.accept()
            except OSError:
                return
            with conn:
                _ = conn.recv(65_536)
                body = b'{"schema_version":"p144.fixture_response.v1","result":"accepted","receipt_id":"cli-receipt"}'
                conn.sendall(b"HTTP/1.1 202 Accepted\r\ncontent-type: application/json\r\ncontent-length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        run = process_adapter_deliveries(config, capability)
    finally:
        stop.set()
        listener.close()

    payload: dict[str, Any] = {
        "status": "ok",
        "run_hash": run["run_hash"],
        "adapter_counters": run["adapter_counters"],
        "transport_counters": run["transport_counters"],
        "forbidden_counters": zero_forbidden_counters(),
    }
    data = canonical_json(payload) + b"\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(data)
    sys.stdout.buffer.write(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
