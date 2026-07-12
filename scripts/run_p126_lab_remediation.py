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

from app.services.p126_lab_remediation import build_release_evidence, load_lab_scenarios, run_lab_remediation  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run P126 strict local ephemeral lab remediation scenarios.")
    parser.add_argument("--input", type=Path, default=Path("evals/p126/input/lab-scenarios.json"))
    parser.add_argument("--output", type=Path, default=Path("evals/p126/lab-report.json"))
    parser.add_argument("--release-evidence", type=Path, default=Path("evals/p126/release-evidence.json"))
    args = parser.parse_args(argv)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.release_evidence.parent.mkdir(parents=True, exist_ok=True)
    scenario_set = load_lab_scenarios(args.input)
    report = run_lab_remediation(scenario_set)
    _atomic_json(args.output, report)
    evidence = build_release_evidence(report, report_path=args.output)
    _atomic_json(args.release_evidence, evidence)
    print(json.dumps({"p126": "ready", "report": str(args.output), "release_evidence": str(args.release_evidence)}, sort_keys=True))
    return 0


def _atomic_json(path: Path, payload: object) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
