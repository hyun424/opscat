#!/usr/bin/env python3
"""Run P61 local shadow connector validation report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.local_shadow_connector_validation import (  # noqa: E402
    build_local_shadow_connector_validation_report,
    write_local_shadow_connector_validation_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P61 local shadow connector validation")
    parser.add_argument("--source", default="evals/shadow/p61_local_shadow_source.json")
    parser.add_argument("--output-json", default="/tmp/opscat-local-shadow-connector-validation-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-local-shadow-connector-validation-latest.md")
    args = parser.parse_args()
    report = build_local_shadow_connector_validation_report(args.source)
    payload = report.to_dict()
    write_local_shadow_connector_validation_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    print(f"Wrote {args.output_md}")
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
