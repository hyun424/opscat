"""Public OpsCat CLI with deterministic, network-free local demo commands."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path

from app.public_contracts import public_contract_manifest
from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import zero_authority_counters


def run_local_demo(output: Path) -> dict[str, object]:
    mode = os.getenv("OPSCAT_MODE", "local")
    target = os.getenv("OPSCAT_TARGET", "fixture://local-demo")
    if mode not in {"local", "test", "fixture", "mock", "sandbox"} or not target.startswith("fixture://"):
        raise ValueError("production_like_demo_configuration_denied")
    events = [
        {"step": "observe", "result": "fixture_signal_collected"},
        {"step": "investigate", "result": "read_only_evidence_bound"},
        {"step": "decide", "result": "local_sandbox_plan_selected"},
        {"step": "validate", "result": "deterministic_replay_complete"},
    ]
    artifact: dict[str, object] = {
        "schema_version": "opscat.local_demo.v1",
        "mode": mode,
        "target": target,
        "network_calls": 0,
        "credential_reads": 0,
        "production_mutations": 0,
        "events": events,
        "authority_counters": zero_authority_counters(),
    }
    artifact["replay_hash"] = stable_hash(artifact)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="opscat")
    subparsers = parser.add_subparsers(dest="command", required=True)
    demo = subparsers.add_parser("demo", help="run the network-free fixture demo")
    demo.add_argument("--output", type=Path, default=Path("opscat-demo-replay.json"))
    subparsers.add_parser("contracts", help="print stable public contracts as JSON")
    args = parser.parse_args(argv)
    if args.command == "contracts":
        print(json.dumps(public_contract_manifest(), indent=2, sort_keys=True))
        return 0
    try:
        artifact = run_local_demo(args.output)
    except ValueError as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({"status": "complete", "replay_hash": artifact["replay_hash"], "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
