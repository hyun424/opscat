"""Explicit-path CLI for the P142 numeric-loopback transport lab."""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, NoReturn, TextIO

from app.services.p142_loopback_transport_lab import (
    LoopbackTransportError,
    list_loopback_receipts,
    load_loopback_transport_config,
    process_loopback_transport,
    validate_loopback_transport_config,
)


class _CliError(ValueError):
    pass


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _CliError(message)


class StopController:
    def __init__(self) -> None:
        self.requested = False
        self.signal_number: int | None = None

    def handle_signal(self, signum: int, _frame: object) -> None:
        self.requested = True
        self.signal_number = signum


def build_parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(prog="opscat-loopback-transport-lab", description="Numeric-loopback-only P142 transport lab")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "process", "list"):
        command = commands.add_parser(name)
        command.add_argument("--config", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--max-cycles", type=int)
    run.add_argument("--forever", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        result = _dispatch(args)
    except (OSError, LoopbackTransportError, _CliError) as exc:
        _emit({"ok": False, "error": str(exc), "error_type": type(exc).__name__}, stream=sys.stderr)
        return 2
    _emit(result)
    return 0


def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    config = load_loopback_transport_config(args.config)
    if args.command == "validate":
        return validate_loopback_transport_config(config)
    if args.command == "process":
        return process_loopback_transport(config)
    if args.command == "list":
        items = list_loopback_receipts(config)
        return {"schema_version": "p142.loopback_transport_receipt_list.v1", "count": len(items), "items": items}
    if args.command == "run":
        if args.forever == (args.max_cycles is not None):
            raise _CliError("choose exactly one of --forever or --max-cycles")
        if args.max_cycles is not None and args.max_cycles <= 0:
            raise _CliError("--max-cycles must be positive")
        controller = StopController()
        with _installed_signal_handlers(controller):
            return _run_loop(config, controller, max_cycles=args.max_cycles)
    raise _CliError("unknown command")


def _run_loop(config: Any, controller: StopController, *, max_cycles: int | None) -> dict[str, Any]:
    cycles = 0
    last: dict[str, Any] | None = None
    last_tick = time.monotonic()
    while not controller.requested and (max_cycles is None or cycles < max_cycles):
        tick = time.monotonic()
        if tick + 5.0 < last_tick:
            raise LoopbackTransportError("monotonic_clock_rollback")
        last_tick = tick
        last = process_loopback_transport(config)
        cycles += 1
        if not controller.requested and (max_cycles is None or cycles < max_cycles):
            time.sleep(1)
    return {
        "schema_version": "p142.loopback_transport_loop.v1",
        "cycles": cycles,
        "stop_requested": controller.requested,
        "signal_number": controller.signal_number,
        "last_result": last,
    }


@contextmanager
def _installed_signal_handlers(controller: StopController) -> Iterator[None]:
    previous: dict[signal.Signals, Any] = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, controller.handle_signal)
    try:
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def _emit(value: Mapping[str, Any], *, stream: TextIO | None = None) -> None:
    output = stream or sys.stdout
    output.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    output.flush()


if __name__ == "__main__":
    raise SystemExit(main())
