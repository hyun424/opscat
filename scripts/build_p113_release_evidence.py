#!/usr/bin/env python3
"""Assemble concise fail-closed P113 release evidence from sealed aggregate artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p113_release_evidence import produce_p113_release_evidence, render_p113_release_markdown  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition-verification", type=Path, required=True)
    parser.add_argument("--freeze-manifest", type=Path, required=True)
    parser.add_argument("--packet-manifest", type=Path, required=True)
    parser.add_argument("--p112-baseline-evaluation", type=Path, required=True)
    parser.add_argument("--diagnosis-evaluation", type=Path, required=True)
    parser.add_argument("--diagnosis-contract-evaluation", type=Path, required=True)
    parser.add_argument("--narrative-evaluation", type=Path, action="append", default=[])
    parser.add_argument("--repeat-evaluation", type=Path)
    parser.add_argument("--cryptographic-review", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args(argv)

    release = produce_p113_release_evidence(
        acquisition_verification=_read_mapping(args.acquisition_verification),
        freeze_manifest=_read_mapping(args.freeze_manifest),
        packet_manifest=_read_mapping(args.packet_manifest),
        p112_baseline_evaluation=_read_mapping(args.p112_baseline_evaluation),
        diagnosis_evaluation=_read_mapping(args.diagnosis_evaluation),
        diagnosis_contract_evaluation=_read_mapping(args.diagnosis_contract_evaluation),
        narrative_evaluations=[_read_mapping(path) for path in args.narrative_evaluation],
        repeat_evaluation=_read_mapping(args.repeat_evaluation) if args.repeat_evaluation else None,
        cryptographic_review=_read_mapping(args.cryptographic_review) if args.cryptographic_review else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(release, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_p113_release_markdown(release), encoding="utf-8")
    print(
        json.dumps(
            {
                "release_qualified": release["release_qualified"],
                "stop_reason": release["stop_reason"],
                "release_evidence_hash": release["release_evidence_hash"],
                "failed_gates": [name for name, passed in release["gates"].items() if not passed],
            },
            sort_keys=True,
        )
    )
    return 0


def _read_mapping(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
