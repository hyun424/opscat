from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.judgment_adapters import cases_from_loghub_rows, cases_from_nab_windows, load_loghub_rows, load_nab_rows  # noqa: E402
from app.services.judgment_dataset import write_judgment_cases  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert repo-local external-style samples into OpsCat judgment cases")
    parser.add_argument("--source", required=True, choices=("loghub", "nab"))
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--dataset", default="seed")
    parser.add_argument("--service", default="benchmark-service")
    args = parser.parse_args()

    if args.source == "loghub":
        cases = cases_from_loghub_rows(load_loghub_rows(args.input))
    elif args.source == "nab":
        cases = cases_from_nab_windows(load_nab_rows(args.input), dataset=args.dataset, service=args.service)
    else:  # pragma: no cover - argparse choices guard this
        parser.error(f"unknown source {args.source}")
    write_judgment_cases(args.output, cases)
    print(f"wrote {len(cases)} judgment case(s) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
