from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.prevention_canary_fixture_matrix import (  # noqa: E402
    CANONICAL_FIXTURE_PATH,
    build_fixture_matrix_evidence,
    evaluate_prevention_canary_fixture_matrix,
    load_prevention_canary_fixture_matrix,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render deterministic P107 canary fixture evidence.")
    parser.add_argument("--fixture-path", "--cases", dest="fixture_path", default=str(CANONICAL_FIXTURE_PATH))
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    fixture_path = Path(args.fixture_path)
    if fixture_path != CANONICAL_FIXTURE_PATH:
        sys.stderr.write(f"fixture path must be {CANONICAL_FIXTURE_PATH}\n")
        return 2

    matrix = load_prevention_canary_fixture_matrix(fixture_path)
    result = evaluate_prevention_canary_fixture_matrix(matrix)

    if args.dry_run:
        payload = {
            "schema_version": "p107.canary_evidence_dry_run.v1",
            "fixture_path": str(CANONICAL_FIXTURE_PATH),
            "fixture_ids": result["fixture_ids"],
            "would_execute": True,
        }
        sys.stdout.write(_json(payload))
        return 0 if result["accepted"] else 1

    evidence = build_fixture_matrix_evidence(matrix)
    if args.output_json is not None:
        args.output_json.write_text(_json(evidence), encoding="utf-8")
    if args.output_md is not None:
        args.output_md.write_text(_markdown(evidence), encoding="utf-8")
    sys.stdout.write(_json(evidence))
    return 0 if evidence["accepted"] else 1


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def _markdown(evidence: dict[str, Any]) -> str:
    lines = [
        "# P107 Canary Fixture Evidence",
        "",
        f"- Fixture path: `{evidence['fixture_path']}`",
        f"- Accepted: `{str(evidence['accepted']).lower()}`",
        f"- Matrix hash: `{evidence['matrix_hash']}`",
        f"- Fixture IDs: `{', '.join(evidence['fixture_ids'])}`",
        "",
        "## Evidence Gates",
    ]
    lines.extend(f"- `{key}`: `{str(value).lower()}`" for key, value in evidence["evidence_gates"].items())
    lines.extend(["", "## Metric Gates"])
    lines.extend(f"- `{key}`: `{str(value).lower()}`" for key, value in evidence["metric_gates"].items())
    lines.extend(["", "## Authority", ""])
    lines.extend(f"- `{key}`: `{value}`" for key, value in evidence["authority_counters"].items())
    if evidence["reasons"]:
        lines.extend(["", "## Reasons"])
        lines.extend(f"- {reason}" for reason in evidence["reasons"])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
