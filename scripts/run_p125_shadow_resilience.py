#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p125_shadow_resilience import build_release_evidence, load_soak_profile, run_shadow_resilience  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run P125 deterministic local shadow resilience soak.")
    parser.add_argument("--profile", type=Path, default=Path("evals/p125/input/soak-profile.json"))
    parser.add_argument("--output", type=Path, default=Path("evals/p125/resilience-report.json"))
    parser.add_argument("--ledger", type=Path, default=Path("evals/p125/resilience-ledger.jsonl"))
    parser.add_argument("--release-evidence", type=Path, default=Path("evals/p125/release-evidence.json"))
    args = parser.parse_args(argv)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    args.release_evidence.parent.mkdir(parents=True, exist_ok=True)
    profile = load_soak_profile(args.profile)
    report, _ = run_shadow_resilience(profile=profile, ledger_path=args.ledger)
    _atomic_json(args.output, report)
    evidence = build_release_evidence(report, report_path=args.output, ledger_path=args.ledger)
    _atomic_json(args.release_evidence, evidence)
    print(json.dumps({"p125": "ready", "report": str(args.output), "ledger": str(args.ledger), "release_evidence": str(args.release_evidence)}, sort_keys=True))
    return 0


def _atomic_json(path: Path, payload: object) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
