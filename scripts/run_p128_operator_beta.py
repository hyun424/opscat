#!/usr/bin/env python3
"""Run P128 operator evidence/replay beta contract generation."""

from __future__ import annotations

import argparse

from app.services.p128_operator_beta import build_p128_operator_beta_contract, write_p128_outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Run OpsCat P128 operator beta UX contract")
    parser.add_argument("--input", default="evals/p128/input/operator-scenarios.json")
    parser.add_argument("--output-json", default="evals/p128/ux-contract.json")
    parser.add_argument("--release-evidence-json", default="evals/p128/release-evidence.json")
    args = parser.parse_args()

    contract = build_p128_operator_beta_contract(args.input)
    evidence = write_p128_outputs(contract, output_json=args.output_json, release_evidence_json=args.release_evidence_json)
    print(
        "OpsCat P128 operator beta "
        f"scenarios={contract['summary']['scenario_count']} "
        f"passed={contract['summary']['passed']} "
        f"release_ready={evidence['gates']['release_ready']} "
        f"output={args.output_json}"
    )


if __name__ == "__main__":
    main()
