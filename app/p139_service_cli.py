"""Explicit-path, credential-free CLI for the P139 local triage service."""

from __future__ import annotations

import argparse
import json
import signal
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.services.p139_local_triage_service import (
    P139ServiceError,
    P139StopController,
    inspect_local_triage_service,
    read_local_triage_service_bundle,
    run_local_triage_service,
    utc_timestamp,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="opscat-triage-service")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate a canonical bundle")
    validate.add_argument("--bundle", required=True, type=Path)
    run = commands.add_parser("run", help="run the local supervisor until a safe stop")
    run.add_argument("--bundle", required=True, type=Path)
    run.add_argument("--base", required=True, type=Path)
    status = commands.add_parser("status", help="read deterministic local health")
    status.add_argument("--bundle", required=True, type=Path)
    status.add_argument("--base", required=True, type=Path)
    status.add_argument("--now", default=None)
    return parser


def _emit(value: dict[str, Any], *, stream: Any = sys.stdout) -> None:
    stream.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    stream.flush()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        bundle = read_local_triage_service_bundle(args.bundle)
        if args.command == "validate":
            _emit(
                {
                    "status": "valid",
                    "service_id": bundle["service_id"],
                    "bundle_hash": bundle["bundle_hash"],
                }
            )
            return 0
        if args.command == "status":
            status = inspect_local_triage_service(
                base_path=args.base,
                bundle=bundle,
                now=args.now or utc_timestamp(),
            )
            _emit(status)
            return 0 if status["health"] in {"ready", "stopped_clean"} else 3
        controller = P139StopController()
        previous_handlers: dict[int, Any] = {}
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, controller.handle_signal)
        try:
            result = run_local_triage_service(
                base_path=args.base,
                bundle=bundle,
                stop_controller=controller,
            )
        finally:
            for restore_signum, handler in previous_handlers.items():
                signal.signal(restore_signum, handler)
        _emit(result)
        return 0
    except (OSError, P139ServiceError) as exc:
        _emit(
            {"status": "failed_closed", "error": str(exc)},
            stream=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
