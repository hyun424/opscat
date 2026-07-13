"""Command-line entrypoint for the independent P131 monitor runtime."""

from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.p131_always_on_monitor import AlwaysOnMonitor, evaluate_watchdog, load_monitor_config, monitor_status_snapshot
from app.services.p133_deadman_outbox import DeadmanOutbox, acknowledge_event, list_outbox, load_deadman_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="opscat-monitor", description="Credential-free local OpsCat monitor runtime")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run the monitor loop")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--max-cycles", type=int)
    run.add_argument("--forever", action="store_true")
    run.add_argument("--no-sleep", action="store_true")

    watchdog = subparsers.add_parser("watchdog", help="Check monitor heartbeat independently")
    watchdog.add_argument("--state", type=Path, required=True)
    watchdog.add_argument("--timeout-seconds", type=int, default=180)

    status = subparsers.add_parser("status", help="Read monitor liveness and readiness")
    status.add_argument("--state", type=Path, required=True)
    status.add_argument("--heartbeat-timeout-seconds", type=int, default=180)
    status.add_argument("--data-stale-after-seconds", type=int, default=300)

    deadman_run = subparsers.add_parser("deadman-run", help="Run the local dead-man outbox")
    deadman_run.add_argument("--config", type=Path, required=True)
    deadman_run.add_argument("--max-cycles", type=int)
    deadman_run.add_argument("--forever", action="store_true")
    deadman_run.add_argument("--no-sleep", action="store_true")

    deadman_check = subparsers.add_parser("deadman-check", help="Run one local dead-man check")
    deadman_check.add_argument("--config", type=Path, required=True)

    outbox_list = subparsers.add_parser("outbox-list", help="List redacted local dead-man events")
    outbox_list.add_argument("--config", type=Path, required=True)

    outbox_ack = subparsers.add_parser("outbox-ack", help="Acknowledge one local dead-man event")
    outbox_ack.add_argument("--config", type=Path, required=True)
    outbox_ack.add_argument("--event-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = _dispatch(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.command == "watchdog":
        return 0 if result.get("healthy") is True else 1
    if args.command == "status":
        return 0 if result.get("live") is True else 1
    if args.command == "deadman-check":
        return 0 if result.get("healthy") is True else 1
    return 0


def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "run":
        if args.forever and args.max_cycles is not None:
            raise ValueError("--forever and --max-cycles are mutually exclusive")
        if not args.forever and args.max_cycles is None:
            raise ValueError("choose --forever or --max-cycles")
        if args.no_sleep and args.max_cycles is None:
            raise ValueError("--no-sleep requires --max-cycles")
        monitor_config = load_monitor_config(args.config)
        if args.forever:
            controller = _SignalStopController()
            with controller.installed():
                return AlwaysOnMonitor(monitor_config).run(
                    max_cycles=None,
                    sleep_enabled=True,
                    stop_reason=controller.reason,
                    wait_for_stop=controller.wait,
                )
        return AlwaysOnMonitor(monitor_config).run(max_cycles=args.max_cycles, sleep_enabled=not args.no_sleep)
    if args.command == "deadman-run":
        if args.forever and args.max_cycles is not None:
            raise ValueError("--forever and --max-cycles are mutually exclusive")
        if not args.forever and args.max_cycles is None:
            raise ValueError("choose --forever or --max-cycles")
        if args.no_sleep and args.max_cycles is None:
            raise ValueError("--no-sleep requires --max-cycles")
        deadman_config = load_deadman_config(args.config)
        if args.forever:
            controller = _SignalStopController()
            with controller.installed():
                return DeadmanOutbox(deadman_config).run(
                    forever=True,
                    stop_reason=controller.reason,
                    wait_for_stop=controller.wait,
                )
        runtime = DeadmanOutbox(deadman_config, sleep=(lambda _seconds: None) if args.no_sleep else None)
        return runtime.run(max_cycles=args.max_cycles)
    if args.command == "deadman-check":
        return DeadmanOutbox(load_deadman_config(args.config)).check_once()
    if args.command == "outbox-list":
        events = list_outbox(load_deadman_config(args.config))
        summaries = [
            {
                "event_id": event["event_id"],
                "incident_id": event["incident_id"],
                "sequence": event["sequence"],
                "transition_kind": event["transition_kind"],
                "occurred_at": event["occurred_at"],
                "reason": event["snapshot"]["reason"],
                "healthy": event["snapshot"]["healthy"],
                "authority_counters": event["authority_counters"],
            }
            for event in events
        ]
        return {"schema_version": "p133.outbox_list.v1", "count": len(summaries), "events": summaries}
    if args.command == "outbox-ack":
        deadman_config = load_deadman_config(args.config)
        return acknowledge_event(deadman_config, args.event_id, now=datetime.now(UTC))
    now = datetime.now(UTC)
    if args.command == "watchdog":
        return evaluate_watchdog(args.state, now=now, heartbeat_timeout_seconds=args.timeout_seconds)
    return monitor_status_snapshot(
        args.state,
        now=now,
        heartbeat_timeout_seconds=args.heartbeat_timeout_seconds,
        data_stale_after_seconds=args.data_stale_after_seconds,
    )


class _SignalStopController:
    """Translate process signals into a normal-control-flow stop request."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._reason: str | None = None

    def reason(self) -> str | None:
        return self._reason

    def wait(self, timeout: float) -> bool:
        return self._event.wait(timeout)

    def _handle(self, signum: int, _frame: object) -> None:
        if self._reason is None:
            self._reason = "sigterm" if signum == signal.SIGTERM else "sigint"
        self._event.set()

    @contextmanager
    def installed(self) -> Iterator[None]:
        previous_term = signal.getsignal(signal.SIGTERM)
        previous_int = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGTERM, self._handle)
        signal.signal(signal.SIGINT, self._handle)
        try:
            yield
        finally:
            signal.signal(signal.SIGTERM, previous_term)
            signal.signal(signal.SIGINT, previous_int)


if __name__ == "__main__":
    raise SystemExit(main())
