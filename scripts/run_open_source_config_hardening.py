#!/usr/bin/env python3
"""Run P37 open-source config hardening fixture."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.open_source_config_hardening import run_open_source_config_hardening_fixture, write_open_source_config_hardening_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P37 open-source config hardening")
    parser.add_argument("--manifest", default="evals/config/p37_config_manifest.json")
    parser.add_argument("--output-json", default="/tmp/opscat-open-source-config-hardening-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-open-source-config-hardening-latest.md")
    args = parser.parse_args()

    report = run_open_source_config_hardening_fixture(args.manifest)
    payload = report.to_dict()
    write_open_source_config_hardening_outputs(payload, output_json=Path(args.output_json), output_md=Path(args.output_md))
    print(f"Wrote {args.output_md}")
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
