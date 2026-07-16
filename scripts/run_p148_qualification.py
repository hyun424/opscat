#!/usr/bin/env python3
"""Generate P148 preliminary or final qualification artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p147_p152_contracts import load_json, validate_current_release_bindings  # noqa: E402
from app.services.p148_reversible_lab import (  # noqa: E402
    P148_CONTRACT,
    generate_p148_preliminary_artifacts,
    generate_p148_release_artifact,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)

    preliminary = subparsers.add_parser("preliminary", help="write report.json and freeze-manifest.json")
    preliminary.add_argument("--project-root", type=Path, default=ROOT)
    preliminary.add_argument("--output-dir", type=Path, required=True)

    final = subparsers.add_parser("final", help="assemble release-evidence.json from supplied review")
    final.add_argument("--output-dir", type=Path, required=True)
    final.add_argument("--report", type=Path, required=True)
    final.add_argument("--freeze-manifest", type=Path, required=True)
    final.add_argument("--final-review", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.mode == "preliminary":
            artifacts = generate_p148_preliminary_artifacts(project_root=args.project_root, output_dir=args.output_dir)
            _print_receipt("preliminary", artifacts)
            return 0
        evidence_path = generate_p148_release_artifact(
            output_dir=args.output_dir,
            report=validate_current_release_bindings(
                ROOT,
                load_json(args.report),
                P148_CONTRACT,
                require_companion_artifacts=True,
            ),
            freeze_manifest=load_json(args.freeze_manifest),
            final_review=load_json(args.final_review),
        )
        _print_receipt("final", {"release_evidence": evidence_path})
        return 0
    except Exception as exc:
        print(json.dumps({"phase": "p148", "status": "blocked", "error_type": type(exc).__name__, "error": str(exc)}, sort_keys=True, separators=(",", ":")), file=sys.stderr)
        return 1


def _print_receipt(mode: str, artifacts: dict[str, Path]) -> None:
    payload: dict[str, Any] = {
        "phase": "p148",
        "mode": mode,
        "artifacts": {key: str(path) for key, path in sorted(artifacts.items())},
    }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
