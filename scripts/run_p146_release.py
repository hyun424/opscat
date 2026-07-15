from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.services.p146_runner import (
    generate_final_release_artifacts,
    generate_preliminary_release_artifacts,
    runner_receipt,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run P146 release artifact generation.")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    preliminary = subparsers.add_parser("preliminary")
    preliminary.add_argument("--project-root", type=Path, default=Path("."))
    preliminary.add_argument("--output-dir", type=Path, required=True)

    final = subparsers.add_parser("final")
    final.add_argument("--project-root", type=Path, default=Path("."))
    final.add_argument("--matrix", type=Path, required=True)
    final.add_argument("--benchmark-report", type=Path, required=True)
    final.add_argument("--freeze-manifest", type=Path, required=True)
    final.add_argument("--final-review", type=Path, required=True)
    final.add_argument("--output-dir", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.mode == "preliminary":
        artifacts = generate_preliminary_release_artifacts(project_root=args.project_root, output_dir=args.output_dir)
        print(json.dumps(runner_receipt(mode="preliminary", artifacts={"release_evidence": artifacts["preliminary_evidence"]}, output_dir=args.output_dir), sort_keys=True, separators=(",", ":")))
        return 0
    if args.mode == "final":
        evidence_path = generate_final_release_artifacts(
            project_root=args.project_root,
            matrix_path=args.matrix,
            benchmark_report_path=args.benchmark_report,
            freeze_manifest_path=args.freeze_manifest,
            final_review_path=args.final_review,
            output_dir=args.output_dir,
        )
        print(json.dumps(runner_receipt(mode="final", artifacts={"release_evidence": evidence_path}, output_dir=args.output_dir), sort_keys=True, separators=(",", ":")))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
