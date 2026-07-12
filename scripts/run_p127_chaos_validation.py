#!/usr/bin/env python3
"""Run P127 deterministic local chaos fail-closed validation."""

from __future__ import annotations

import argparse

from app.services.p127_chaos_validation import run_p127_chaos_validation, write_p127_outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Run OpsCat P127 chaos validation")
    parser.add_argument("--input", default="evals/p127/input/chaos-scenarios.json")
    parser.add_argument("--output-json", default="evals/p127/chaos-report.json")
    parser.add_argument("--release-evidence-json", default="evals/p127/release-evidence.json")
    args = parser.parse_args()

    report = run_p127_chaos_validation(args.input)
    evidence = write_p127_outputs(report, output_json=args.output_json, release_evidence_json=args.release_evidence_json)
    print(
        "OpsCat P127 chaos validation "
        f"cases={report['summary']['case_count']} "
        f"passed={report['summary']['passed']} "
        f"release_ready={evidence['gates']['release_ready']} "
        f"output={args.output_json}"
    )


if __name__ == "__main__":
    main()
