from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

QUEUE_PROVENANCE = "p105-queue-provenance-hashes.json"
DEPLOY_PROVENANCE = "p105-deploy-provenance-hashes.json"


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a JSON object")
    return payload


def _artifact_tamper_code(kind: str, artifact_name: str) -> str:
    if kind == "queue":
        if artifact_name == "p105-queue-public-telemetry.jsonl":
            return "queue_telemetry_tamper"
        if artifact_name == "p105-queue-private-injection-ledger.json":
            return "queue_private_ledger_tamper"
        if artifact_name == "p105-queue-harness-manifest.json":
            return "queue_manifest_tamper"
        return "queue_artifact_tamper"
    if artifact_name == "p105-deploy-rollback-evidence.json":
        return "deploy_rollback_tamper"
    if artifact_name == "p105-deploy-public-telemetry.jsonl":
        return "deploy_telemetry_tamper"
    if artifact_name == "p105-deploy-harness-manifest.json":
        return "deploy_manifest_tamper"
    return "deploy_artifact_tamper"


def _verify_manifest(manifest_path: Path, *, kind: str) -> list[str]:
    errors: list[str] = []
    try:
        manifest = _read_json(manifest_path)
    except (OSError, json.JSONDecodeError, ValueError):
        return [f"{kind}_manifest_unreadable"]
    base_dir = manifest_path.parent
    artifact_paths = manifest.get("artifact_paths")
    provenance_name = QUEUE_PROVENANCE if kind == "queue" else DEPLOY_PROVENANCE
    if isinstance(artifact_paths, dict):
        value = artifact_paths.get("provenance_hashes")
        if isinstance(value, str):
            provenance_name = value
    provenance_path = base_dir / provenance_name
    try:
        provenance = _read_json(provenance_path)
    except (OSError, json.JSONDecodeError, ValueError):
        return [f"{kind}_provenance_hash_manifest_tamper"]
    expected_hashes = provenance.get("artifact_hashes")
    if not isinstance(expected_hashes, dict) or not expected_hashes:
        errors.append(f"{kind}_provenance_hash_manifest_tamper")
        return errors
    for artifact_name, expected_hash in sorted(expected_hashes.items()):
        if not isinstance(artifact_name, str) or not isinstance(expected_hash, str):
            errors.append(f"{kind}_provenance_hash_manifest_tamper")
            continue
        artifact_path = base_dir / artifact_name
        if not artifact_path.exists():
            errors.append(_artifact_tamper_code(kind, artifact_name))
            continue
        actual_hash = _sha256_path(artifact_path)
        if actual_hash != expected_hash:
            errors.append(_artifact_tamper_code(kind, artifact_name))
    if manifest.get("program_version") != provenance.get("program_version"):
        errors.append(f"{kind}_provenance_hash_manifest_tamper")
    if manifest.get("command_argv_sha256") != provenance.get("command_argv_sha256"):
        errors.append(f"{kind}_provenance_hash_manifest_tamper")
    return sorted(set(errors))


def _compare_reruns(first_manifest: Path, second_manifest: Path, *, kind: str) -> list[str]:
    first = _read_json(first_manifest)
    provenance_name = QUEUE_PROVENANCE if kind == "queue" else DEPLOY_PROVENANCE
    artifact_paths = first.get("artifact_paths")
    if isinstance(artifact_paths, dict) and isinstance(artifact_paths.get("provenance_hashes"), str):
        provenance_name = str(artifact_paths["provenance_hashes"])
    names = sorted(_read_json(first_manifest.parent / provenance_name).get("artifact_hashes", {}))
    names.append(provenance_name)
    errors: list[str] = []
    for name in names:
        if (first_manifest.parent / name).read_bytes() != (second_manifest.parent / name).read_bytes():
            errors.append(f"{kind}_rerun_not_byte_identical")
            break
    return errors


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify P105 source-expansion artifact hashes and fail closed on tamper.")
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--eligibility", type=Path)
    parser.add_argument("--dejavu-manifest", type=Path)
    parser.add_argument("--queue-manifest", type=Path)
    parser.add_argument("--queue-rerun-manifest", type=Path)
    parser.add_argument("--deploy-manifest", type=Path)
    parser.add_argument("--deploy-rerun-manifest", type=Path)
    parser.add_argument("--release-dir", type=Path)
    parser.add_argument("--expect-byte-identical-reruns", action="store_true")
    parser.add_argument("--expect-tamper-fixtures-fail-closed", action="store_true")
    parser.add_argument("--output-json", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    errors: list[str] = []
    verified: dict[str, Any] = {}
    if args.queue_manifest:
        queue_errors = _verify_manifest(args.queue_manifest, kind="queue")
        verified["queue_manifest"] = str(args.queue_manifest)
        errors.extend(queue_errors)
        if args.expect_byte_identical_reruns and args.queue_rerun_manifest:
            errors.extend(_compare_reruns(args.queue_manifest, args.queue_rerun_manifest, kind="queue"))
    if args.deploy_manifest:
        deploy_errors = _verify_manifest(args.deploy_manifest, kind="deploy")
        verified["deploy_manifest"] = str(args.deploy_manifest)
        errors.extend(deploy_errors)
        if args.expect_byte_identical_reruns and args.deploy_rerun_manifest:
            errors.extend(_compare_reruns(args.deploy_manifest, args.deploy_rerun_manifest, kind="deploy"))
    for optional_name in ("registry", "eligibility", "dejavu_manifest"):
        optional_path = getattr(args, optional_name)
        if optional_path is not None:
            verified[optional_name] = {"path": str(optional_path), "sha256": _sha256_path(optional_path) if optional_path.exists() else None}
            if not optional_path.exists():
                errors.append(f"{optional_name}_missing")
    result = {
        "expect_tamper_fixtures_fail_closed": args.expect_tamper_fixtures_fail_closed,
        "release_gate": {"p106_unlocked": False, "release_qualified": False},
        "validation_error_codes": sorted(set(errors)),
        "verified": verified,
    }
    if args.output_json:
        _write_json(args.output_json, result)
    if errors:
        sys.stderr.write(json.dumps(result, sort_keys=True) + "\n")
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
