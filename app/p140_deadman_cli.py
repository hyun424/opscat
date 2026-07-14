"""Explicit-path CLI for the P140 P139 dead-man adapter."""

from __future__ import annotations

import argparse
import json
import signal
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn, TextIO

from app.services.p133_deadman_outbox import P133DeadmanError
from app.services.p140_p139_deadman_adapter import (
    P140AdapterError,
    P140StopController,
    check_p139_deadman_once,
    load_p140_config,
    run_p139_deadman_adapter,
)


class _CliError(ValueError):
    pass


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _CliError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(prog="opscat-triage-deadman", description="Credential-free P139 dead-man adapter")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate and bind an adapter config")
    validate.add_argument("--config", type=Path, required=True)

    check = commands.add_parser("check", help="run one adapter check")
    check.add_argument("--config", type=Path, required=True)
    check.add_argument("--now", default=None, help="UTC ISO-8601 timestamp for deterministic checks")

    run = commands.add_parser("run", help="run the adapter loop")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--max-cycles", type=int)
    run.add_argument("--forever", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        result = _dispatch(args)
    except (OSError, P133DeadmanError, P140AdapterError, _CliError) as exc:
        _emit({"ok": False, "error": str(exc)}, stream=sys.stderr)
        return 2
    _emit(result)
    if args.command == "check":
        return 0 if result.get("healthy") is True else 1
    return 0


def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    config = load_p140_config(args.config)
    if args.command == "validate":
        return {
            "status": "valid",
            "adapter_id": config.adapter_id,
            "adapter_config_hash": config.config_hash,
        }
    if args.command == "check":
        return check_p139_deadman_once(config, now=_parse_utc(args.now))
    if args.command == "run":
        if args.forever == (args.max_cycles is not None):
            raise _CliError("choose exactly one of --forever or --max-cycles")
        controller = P140StopController()
        with _installed_signal_handlers(controller):
            return run_p139_deadman_adapter(
                config,
                max_cycles=args.max_cycles,
                forever=args.forever,
                stop_controller=controller,
            )
    raise _CliError("unknown command")


def _parse_utc(value: str | None) -> datetime | None:
    if value is None:
        return None
    candidate = value
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise _CliError("--now must be an ISO-8601 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise _CliError("--now must be timezone-aware UTC")
    return parsed.astimezone(UTC)


@contextmanager
def _installed_signal_handlers(controller: P140StopController) -> Iterator[None]:
    previous_handlers: dict[signal.Signals, Any] = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, controller.handle_signal)
    try:
        yield
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def _emit(value: dict[str, Any], *, stream: TextIO | None = None) -> None:
    output = stream or sys.stdout
    output.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    output.flush()


if __name__ == "__main__":
    raise SystemExit(main())
