#!/usr/bin/env python3
"""Run the P11 local/mock incident corpus audit."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.judgment_corpus import (  # noqa: E402
    DEFAULT_CORPUS_PATH,
    audit_judgment_corpus,
    build_seed_corpus,
    load_corpus_pack,
    write_corpus_audit_outputs,
    write_corpus_pack,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit OpsCat P11 incident corpus quality")
    parser.add_argument("--corpus", default=None, help="Existing corpus JSON to audit. Defaults to generated seed corpus when omitted.")
    parser.add_argument("--write-corpus", default=None, help="Write deterministic generated corpus JSON to this path before auditing.")
    parser.add_argument("--output-json", default=None, help="Write audit JSON report")
    parser.add_argument("--output-md", default=None, help="Write audit Markdown report")
    args = parser.parse_args()

    if args.write_corpus:
        cases = build_seed_corpus()
        write_corpus_pack(args.write_corpus, cases)
    elif args.corpus:
        cases = load_corpus_pack(args.corpus)
    elif DEFAULT_CORPUS_PATH.exists():
        cases = load_corpus_pack(DEFAULT_CORPUS_PATH)
    else:
        cases = build_seed_corpus()

    audit = audit_judgment_corpus(cases)
    write_corpus_audit_outputs(audit, output_json=args.output_json, output_md=args.output_md)
    if args.output_md:
        print(f"wrote markdown report to {Path(args.output_md)}")
    if args.output_json:
        print(f"wrote json report to {Path(args.output_json)}")
    print(f"cases={audit.total_cases} archetypes={audit.archetype_count} passed={audit.passed}")
    return 0 if audit.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
