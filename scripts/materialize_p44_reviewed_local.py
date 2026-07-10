from __future__ import annotations

# ruff: noqa: E402, I001

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parsed = json.loads(line)
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _load_raw_records(raw_p44: str | None, raw_manifest: str | None) -> tuple[list[dict[str, Any]], list[Path]]:
    if raw_p44:
        path = Path(raw_p44)
        return _read_jsonl(path), [path]
    if not raw_manifest:
        raise ValueError("one of --raw-p44 or --raw-manifest is required")
    manifest_path = Path(raw_manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    paths: list[Path] = []
    for source in manifest.get("sources", []):
        if not isinstance(source, dict):
            continue
        source_path = Path(str(source.get("path") or source.get("local_path") or source.get("local_materialized_path") or ""))
        if not source_path.is_absolute():
            source_path = manifest_path.parent / source_path
        paths.append(source_path)
        records.extend(_read_jsonl(source_path))
    return records, paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize reviewed-local P44 public records and sidecars.")
    parser.add_argument("--raw-p44", default=None, help="Test-mode raw P44 JSONL input.")
    parser.add_argument("--raw-manifest", default=None, help="Production flat manifest listing raw P44 JSONL inputs.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--reviewed-by", required=True)
    parser.add_argument("--license-id", required=True)
    parser.add_argument("--citation-id", required=True)
    parser.add_argument("--source-cap", type=int, default=2000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    records, source_paths = _load_raw_records(args.raw_p44, args.raw_manifest)
    sampled = sorted(records, key=lambda row: _stable_json({key: value for key, value in row.items() if key != "private_label"}))[: args.source_cap]
    public_records = []
    for record in sampled:
        copied = dict(record)
        copied.pop("private_label", None)
        public_records.append(copied)

    records_path = output / "p44-reviewed-local-public-records.jsonl"
    records_path.write_text("\n".join(json.dumps(record, sort_keys=True) for record in public_records) + "\n", encoding="utf-8")
    records_hash = hashlib.sha256(records_path.read_bytes()).hexdigest()

    privacy_name = "p105-privacy-redaction-manifest.json"
    license_name = "p105-license-manifest.json"
    citation_name = "p105-citation-manifest.json"
    provenance_name = "p105-provenance-hash-manifest.json"
    _write_json(
        output / privacy_name,
        {
            "schema_version": "p105.privacy_redaction.v1",
            "review_status": "reviewed_redacted",
            "reviewed_by": args.reviewed_by,
            "raw_private_labels_embedded": False,
        },
    )
    _write_json(
        output / license_name,
        {
            "schema_version": "p105.license.v1",
            "sources": [{"source_id": "p44:reviewed-local", "license_id": args.license_id}],
        },
    )
    _write_json(
        output / citation_name,
        {
            "schema_version": "p105.citation.v1",
            "citations": [{"citation_id": args.citation_id, "source_id": "p44:reviewed-local"}],
        },
    )
    _write_json(
        output / provenance_name,
        {
            "schema_version": "p105.provenance_hash.v1",
            "public_records_sha256": records_hash,
            "source_paths": [str(path) for path in source_paths],
        },
    )
    manifest = {
        "schema_version": "p105.reviewed_p44_local_manifest.v3",
        "review_redaction_status": "reviewed_redacted",
        "source_cap": args.source_cap,
        "privacy_manifest_path": privacy_name,
        "license_manifest_path": license_name,
        "citation_manifest_path": citation_name,
        "provenance_hash_manifest_path": provenance_name,
        "sources": [
            {
                "source_id": "p44:reviewed-local",
                "family": "multi",
                "local_materialized_path": str(records_path),
                "local_source_hash": records_hash,
                "record_count": len(public_records),
                "private_label_format": "separate_private_ledger_required",
                "partition_format": "pre_label_partition",
            }
        ],
    }
    _write_json(output / "p44-reviewed-local-manifest.json", manifest)
    print(json.dumps({"manifest_path": str(output / "p44-reviewed-local-manifest.json"), "record_count": len(public_records)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
