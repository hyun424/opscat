"""Explicit-path CLI for the P141 local notification authority simulator."""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn, TextIO

from app.services.p133_deadman_outbox import P133DeadmanError
from app.services.p141_notification_authority import (
    NotificationAuthorityError,
    list_notification_envelopes,
    list_simulated_receipts,
    load_notification_config,
    process_pending_notifications,
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
    parser = _JsonArgumentParser(prog="opscat-notification-authority", description="Local simulated notification authority")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "process", "list-envelopes", "list-receipts"):
        command = commands.add_parser(name)
        command.add_argument("--config", type=Path, required=True)
        if name == "process":
            command.add_argument("--now", default=None)
    run = commands.add_parser("run")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--max-cycles", type=int)
    run.add_argument("--forever", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        result = _dispatch(args)
    except (OSError, P133DeadmanError, NotificationAuthorityError, _CliError) as exc:
        _emit({"ok": False, "error": str(exc), "error_type": type(exc).__name__}, stream=sys.stderr)
        return 2
    _emit(result)
    return 0


def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    config = load_notification_config(args.config)
    if args.command == "validate":
        return {"status": "valid", "simulator_id": config.simulator_id, "config_hash": config.config_hash}
    if args.command == "process":
        return process_pending_notifications(config, now=_parse_utc(args.now))
    if args.command == "list-envelopes":
        items = list_notification_envelopes(config)
        return {"schema_version": "p141.notification_envelope_list.v1", "count": len(items), "items": items}
    if args.command == "list-receipts":
        items = list_simulated_receipts(config)
        return {"schema_version": "p141.simulated_delivery_receipt_list.v1", "count": len(items), "items": items}
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
    while not controller.requested and (max_cycles is None or cycles < max_cycles):
        last = process_pending_notifications(config)
        cycles += 1
        if not controller.requested and (max_cycles is None or cycles < max_cycles):
            time.sleep(config.poll_interval_seconds)
    return {
        "schema_version": "p141.notification_loop.v1",
        "cycles": cycles,
        "stop_requested": controller.requested,
        "signal_number": controller.signal_number,
        "last_result": last,
        "delivered_count": 0,
        "acknowledged_count": 0,
    }


def _parse_utc(value: str | None) -> datetime | None:
    if value is None:
        return None
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise _CliError("--now must be an ISO-8601 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise _CliError("--now must be timezone-aware UTC")
    return parsed.astimezone(UTC)


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


def _emit(value: MappingLike, *, stream: TextIO | None = None) -> None:
    output = stream or sys.stdout
    output.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    output.flush()


MappingLike = dict[str, Any]


if __name__ == "__main__":
    raise SystemExit(main())
