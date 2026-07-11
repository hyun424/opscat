#!/usr/bin/env python3
"""Build an atomic P115-008 frozen release-evidence JSON bundle."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p115_release_evidence import build_p115_release_evidence, render_p115_release_markdown  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--safe-null-baseline", type=Path, required=True)
    parser.add_argument("--deterministic-baseline", type=Path, required=True)
    parser.add_argument("--evaluator-report", type=Path, required=True)
    parser.add_argument("--p116-release-evidence", type=Path)
    parser.add_argument("--expected-hashes", type=Path)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--builder-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args(argv)

    release = build_p115_release_evidence(
        safe_null_baseline=_read_mapping(args.safe_null_baseline),
        deterministic_baseline=_read_mapping(args.deterministic_baseline),
        evaluator_report=_read_mapping(args.evaluator_report),
        p116_release_evidence=_read_mapping(args.p116_release_evidence) if args.p116_release_evidence else None,
        expected_hashes=_read_mapping(args.expected_hashes) if args.expected_hashes else None,
        reviewer_identity={"id": args.reviewer_id},
        builder_identity={"id": args.builder_id},
    )
    _atomic_write(args.output, json.dumps(release, indent=2, sort_keys=True, ensure_ascii=True) + "\n")
    if args.markdown_output:
        _atomic_write(args.markdown_output, render_p115_release_markdown(release))
    print(
        json.dumps(
            {
                "contract_ready": release["contract_ready"],
                "outcome_qualified": release["outcome_qualified"],
                "release_status": release["release_status"],
                "release_evidence_hash": release["release_evidence_hash"],
                "failed_gates": [name for name, passed in release["gates"].items() if not passed],
            },
            sort_keys=True,
        )
    )
    return 0


def _read_mapping(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise SystemExit(f"expected JSON object: {path}")
    return dict(value)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
