from __future__ import annotations

import hashlib
import json
import shutil
import socket
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.p143_egress_contract_lab import process_egress_contracts
from app.services.p144_provider_adapter_lab import AdapterConfig, ReceiverCapability, issue_receiver_capability, load_adapter_config
from tests.fixtures.p141.builders import write_json
from tests.fixtures.p143.builders import P143Fixture, build_p143_fixture

ROOT = Path(__file__).resolve().parents[3]


@dataclass
class P144Fixture:
    root: Path
    p143: P143Fixture
    config_path: Path
    config: AdapterConfig
    listener: socket.socket
    capability: ReceiverCapability
    responses: list[bytes] = field(default_factory=list)
    requests: list[bytes] = field(default_factory=list)
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return

        def serve() -> None:
            while not self._stop.is_set():
                try:
                    conn, _addr = self.listener.accept()
                except OSError:
                    return
                with conn:
                    self.requests.append(conn.recv(65_536))
                    response = self.responses.pop(0) if self.responses else accepted_response()
                    conn.sendall(response)

        self._thread = threading.Thread(target=serve, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self.listener.close()


def build_p144_fixture(tmp_path: Path, **overrides: Any) -> P144Fixture:
    digest = hashlib.sha256(str(tmp_path.resolve()).encode("utf-8")).hexdigest()[:20].translate(str.maketrans("0123456789", "abcdefghij"))
    root = Path("/private/tmp") / ("p144lab-" + digest)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    p143 = build_p143_fixture(root / "dependency")
    process_egress_contracts(p143.config)
    _copy_release_tree(ROOT / "evals/p143", p143.root)
    eval_root = root / "evals"
    _copy_release_tree(ROOT / "evals/p142", eval_root / "p142")
    _copy_release_tree(ROOT / "evals/p141", eval_root / "p141")
    (eval_root / "p133").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "evals/p133/release-evidence.json", eval_root / "p133/release-evidence.json")
    raw: dict[str, Any] = {
        "schema_version": "p144.adapter_config.v1",
        "workspace_root": str(root),
        "p143_artifact_root": str(p143.root),
        "p142_artifact_root": str(eval_root / "p142"),
        "state_root": "state",
        "adapter_root": "state/adapter",
        "journal_root": "state/journal",
        "receipt_root": "state/receipt",
        "cursor_path": "state/cursor/cursor.json",
        "lease_path": "state/lease/lease.lock",
        "max_sources_per_run": 2,
        "max_attempts_per_delivery": 3,
        "max_request_bytes": 16384,
        "max_response_bytes": 8192,
        "max_total_bytes_per_run": 131072,
        "max_elapsed_ms_per_delivery": 5000,
        "max_retry_after_ms": 1000,
        "connect_timeout_ms": 500,
        "read_timeout_ms": 500,
    }
    raw.update(overrides)
    config_path = root / "config" / "p144.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(config_path, raw)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    return P144Fixture(root=root, p143=p143, config_path=config_path, config=load_adapter_config(config_path), listener=listener, capability=issue_receiver_capability(listener))


def accepted_response(receipt_id: str = "local-receipt") -> bytes:
    body = json.dumps({"schema_version": "p144.fixture_response.v1", "result": "accepted", "receipt_id": receipt_id}, separators=(",", ":")).encode()
    return b"HTTP/1.1 202 Accepted\r\ncontent-type: application/json\r\ncontent-length: " + str(len(body)).encode() + b"\r\nx-extra: ignored\r\n\r\n" + body


def response(status: int, body: dict[str, Any] | bytes = b"", headers: dict[str, str] | None = None) -> bytes:
    body_bytes = json.dumps(body, separators=(",", ":")).encode() if isinstance(body, dict) else body
    merged = {"content-length": str(len(body_bytes)), **(headers or {})}
    header_bytes = b"".join(f"{key}: {value}\r\n".encode("ascii") for key, value in merged.items())
    return f"HTTP/1.1 {status} X\r\n".encode("ascii") + header_bytes + b"\r\n" + body_bytes


def _copy_release_tree(source: Path, target: Path) -> None:
    for relative in ("output/release-evidence.json", "output/canonical-matrix.json", "output/freeze-manifest.json", "final-implementation-review.json", "input"):
        src = source / relative
        dst = target / relative
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
