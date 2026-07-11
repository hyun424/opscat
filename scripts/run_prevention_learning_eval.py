from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p108_release_evidence import (  # noqa: E402
    CANONICAL_FIXTURE_PATH,
    DEFAULT_TRUSTED_NOW,
    SIX_RELEASE_GATE_KEYS,
    build_prevention_learning_evidence,
    evaluate_prevention_learning_fixture_matrix,
    load_prevention_learning_fixture_matrix,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render deterministic P108 prevention learning evidence.")
    parser.add_argument("--fixture-path", "--cases", dest="fixture_path", default=str(CANONICAL_FIXTURE_PATH))
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    parser.add_argument("--trusted-now", default=DEFAULT_TRUSTED_NOW)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    fixture_path = Path(args.fixture_path)
    if fixture_path != CANONICAL_FIXTURE_PATH:
        sys.stderr.write(f"fixture path must be {CANONICAL_FIXTURE_PATH}\n")
        return 2

    matrix = load_prevention_learning_fixture_matrix(fixture_path)
    result = evaluate_prevention_learning_fixture_matrix(matrix)
    if matrix.get("schema_version") != "p108.learning_fixture_matrix.v1":
        sys.stderr.write("fixture schema must be p108.learning_fixture_matrix.v1\n")
        return 2

    if args.dry_run:
        payload = {
            "schema_version": "p108.learning_eval_dry_run.v1",
            "fixture_path": str(CANONICAL_FIXTURE_PATH),
            "trusted_now": args.trusted_now,
            "fixture_ids": result["fixture_ids"],
            "six_release_gates": {key: False for key in SIX_RELEASE_GATE_KEYS},
            "would_execute": True,
        }
        sys.stdout.write(_json(payload))
        return 0 if result["accepted"] else 1

    evidence = build_prevention_learning_evidence(matrix, trusted_now=args.trusted_now)
    if args.output_json is not None:
        args.output_json.write_text(_json(evidence), encoding="utf-8")
    if args.output_md is not None:
        args.output_md.write_text(_markdown(evidence), encoding="utf-8")
    sys.stdout.write(_json(evidence))
    return 0 if evidence["accepted"] else 1


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def _markdown(evidence: Mapping[str, Any]) -> str:
    lines = [
        "# P108 Prevention Learning Evidence",
        "",
        f"- Release schema: `{evidence['release_schema_version']}`",
        f"- Fixture path: `{evidence['fixture_path']}`",
        f"- Accepted: `{str(evidence['accepted']).lower()}`",
        f"- Matrix hash: `{evidence['matrix_hash']}`",
        f"- Fixture IDs: `{', '.join(evidence['fixture_ids'])}`",
        "",
        "## Six Release Gates",
    ]
    lines.extend(f"- `{key}`: `{str(value).lower()}`" for key, value in evidence["six_release_gates"].items())
    lines.extend(["", "## Statistical Support"])
    for key, value in evidence["statistical_support"].items():
        lines.append(f"- `{key}`: `{value}`")
    if evidence["metric_failures"]:
        lines.extend(["", "## Metric Failures"])
        lines.extend(f"- `{key}`: `{value}`" for key, value in evidence["metric_failures"].items())
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
