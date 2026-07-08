#!/usr/bin/env python3
"""Run P48 hypothesis re-ranker report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.hypothesis_reranker import build_hypothesis_reranker_report, write_hypothesis_reranker_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P48 hypothesis re-ranker report")
    parser.add_argument("--cases", default="evals/investigator/p48_rerank_cases.json")
    parser.add_argument("--output-json", default="/tmp/opscat-hypothesis-reranker-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-hypothesis-reranker-latest.md")
    args = parser.parse_args()
    report = build_hypothesis_reranker_report(args.cases)
    payload = report.to_dict()
    write_hypothesis_reranker_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    print(f"Wrote {args.output_md}")
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
