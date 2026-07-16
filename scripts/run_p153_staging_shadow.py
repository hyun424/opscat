#!/usr/bin/env python3
"""Run P153 qualification, final release assembly, or explicit live shadow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p147_p152_contracts import load_json, write_canonical_json  # noqa: E402
from app.services.p153_staging_shadow import (  # noqa: E402
    RecordedReadOnlyTransport,
    UrllibReadOnlyTransport,
    assemble_p153_release_evidence,
    build_p153_freeze_manifest,
    load_p153_profile,
    run_p153_shadow_cycle,
    validate_p153_final_review,
    validate_p153_freeze_manifest,
    validate_p153_release_evidence,
    validate_p153_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)

    preliminary = subparsers.add_parser("preliminary")
    preliminary.add_argument("--profile", type=Path, default=Path("evals/p153/input/staging-shadow-profile.json"))
    preliminary.add_argument("--output-dir", type=Path, default=Path("evals/p153/output"))

    final = subparsers.add_parser("final")
    final.add_argument("--report", type=Path, required=True)
    final.add_argument("--freeze-manifest", type=Path, required=True)
    final.add_argument("--final-review", type=Path, required=True)
    final.add_argument("--output-dir", type=Path, default=Path("evals/p153/output"))

    live = subparsers.add_parser("live")
    live.add_argument("--profile", type=Path, required=True)
    live.add_argument("--output-dir", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.mode == "preliminary":
            profile = load_p153_profile(args.profile)
            report = run_p153_shadow_cycle(
                project_root=ROOT,
                profile=profile,
                output_dir=args.output_dir,
                transport=RecordedReadOnlyTransport.from_profile(profile),
                reset_state=True,
            )
            freeze = build_p153_freeze_manifest(project_root=ROOT, report=report)
            write_canonical_json(args.output_dir / "freeze-manifest.json", freeze)
            print(json.dumps({"mode": "preliminary", "report_hash": report["report_hash"], "manifest_hash": freeze["manifest_hash"]}, sort_keys=True))
            return 0
        if args.mode == "live":
            profile = load_json(args.profile)
            report = run_p153_shadow_cycle(
                project_root=ROOT,
                profile=profile,
                output_dir=args.output_dir,
                transport=UrllibReadOnlyTransport(),
                mode="live",
            )
            print(json.dumps({"mode": "live", "report_hash": report["report_hash"], "outcome": report["judgment"]["outcome"]}, sort_keys=True))
            return 0

        report = validate_p153_report(load_json(args.report))
        freeze = validate_p153_freeze_manifest(load_json(args.freeze_manifest))
        review = validate_p153_final_review(load_json(args.final_review), report=report, freeze_manifest=freeze)
        release = assemble_p153_release_evidence(report=report, freeze_manifest=freeze, final_review=review)
        write_canonical_json(args.output_dir / "release-evidence.json", release)
        validate_p153_release_evidence(release, project_root=ROOT)
        print(json.dumps({"mode": "final", "release_status": release["release_status"], "evidence_hash": release["evidence_hash"]}, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"phase": "p153", "status": "blocked", "error_type": type(exc).__name__, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
