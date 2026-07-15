"""Explicit-path CLI for the P143 provider-neutral egress contract lab."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NoReturn

from app.services.p143_egress_contract_lab import (
    EgressContractError,
    list_egress_results,
    load_egress_contract_config,
    process_egress_contracts,
    validate_egress_contract_config,
)


class _CliError(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _CliError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="opscat-egress-contract-lab")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "process", "list"):
        command = commands.add_parser(name)
        command.add_argument("--config", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--max-cycles", type=int, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        result = _dispatch(args)
    except (OSError, EgressContractError, _CliError) as exc:
        _emit({"ok": False, "error": str(exc), "error_type": type(exc).__name__}, stderr=True)
        return 2
    _emit(result)
    return 0


def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    config = load_egress_contract_config(args.config)
    if args.command == "validate":
        return validate_egress_contract_config(config)
    if args.command == "process":
        return process_egress_contracts(config)
    if args.command == "list":
        items = list_egress_results(config)
        return {"schema_version": "p143.capability_result_list.v1", "count": len(items), "items": items}
    if args.command == "run":
        if args.max_cycles <= 0:
            raise _CliError("--max-cycles must be positive")
        last: dict[str, Any] | None = None
        for _index in range(args.max_cycles):
            last = process_egress_contracts(config)
            time.sleep(0)
        return {"schema_version": "p143.egress_contract_loop.v1", "cycles": args.max_cycles, "last_result": last}
    raise _CliError("unknown command")


def _emit(value: dict[str, Any], *, stderr: bool = False) -> None:
    stream = sys.stderr if stderr else sys.stdout
    stream.write(json.dumps(value, separators=(",", ":")) + "\n")
    stream.flush()


if __name__ == "__main__":
    raise SystemExit(main())
