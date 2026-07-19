#!/usr/bin/env python3
"""Materialize exact P176 release inputs from a disposable live-lab run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p176_live_bridge import P176LiveBridgeError, materialize_live_release_inputs  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--reviewed-apply-plan-artifact", type=Path)
    parser.add_argument("--reviewed-teardown-plan-artifact", type=Path)
    parser.add_argument("--reviewed-cost-cutoff-apply-plan-artifact", type=Path)
    parser.add_argument("--reviewed-cost-cutoff-destroy-plan-artifact", type=Path)
    args = parser.parse_args(argv)

    try:
        result = materialize_live_release_inputs(
            args.run_dir,
            reviewed_apply_plan_artifact_path=args.reviewed_apply_plan_artifact,
            reviewed_teardown_plan_artifact_path=args.reviewed_teardown_plan_artifact,
            reviewed_cost_cutoff_apply_plan_artifact_path=args.reviewed_cost_cutoff_apply_plan_artifact,
            reviewed_cost_cutoff_destroy_plan_artifact_path=args.reviewed_cost_cutoff_destroy_plan_artifact,
        )
    except (P176LiveBridgeError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "phase": "p176",
                    "status": "blocked",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    print(json.dumps({"phase": "p176", **result.as_dict()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
