#!/usr/bin/env python3
"""Evaluator-only subprocess boundary for deterministic P139 service tests."""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p139_local_triage_service import (  # noqa: E402
    P139InjectedCrash,
    P139ServiceError,
    P139StopController,
    read_local_triage_service_bundle,
    run_local_triage_service_for_evaluation,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--now", action="append", required=True)
    parser.add_argument("--crash-after", default=None)
    parser.add_argument("--real-sleep", action="store_true")
    args = parser.parse_args()
    try:
        controller = P139StopController()
        previous = {signum: signal.getsignal(signum) for signum in (signal.SIGINT, signal.SIGTERM)}
        for signum in previous:
            signal.signal(signum, controller.handle_signal)
        try:
            result = run_local_triage_service_for_evaluation(
                base_path=args.base,
                bundle=read_local_triage_service_bundle(args.bundle),
                now_values=tuple(args.now),
                stop_controller=controller,
                monotonic=time.monotonic if args.real_sleep else (lambda: 1.0),
                sleep=time.sleep if args.real_sleep else (lambda _: None),
                crash_after=args.crash_after,
            )
        finally:
            for restore_signum, handler in previous.items():
                signal.signal(restore_signum, handler)
    except P139InjectedCrash as exc:
        print(json.dumps({"status": "injected_crash", "boundary": str(exc)}))
        return 75
    except (OSError, P139ServiceError) as exc:
        print(json.dumps({"status": "failed_closed", "error": str(exc)}))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
