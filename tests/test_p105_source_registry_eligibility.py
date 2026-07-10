from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REGISTRY_SCRIPT = Path("scripts/build_p105_source_registry.py")


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _write_json(path: Path, payload: Any) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _run_registry(tmp_path: Path, manifests: list[Path], ledger: Path) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    registry = tmp_path / "p105-reviewed-source-registry.json"
    eligibility = tmp_path / "p105-source-eligibility-manifest.json"
    command = [
        sys.executable,
        str(REGISTRY_SCRIPT),
        *[item for manifest in manifests for item in ("--candidate-manifest", str(manifest))],
        "--review-ledger",
        str(ledger),
        "--output-registry",
        str(registry),
        "--output-eligibility",
        str(eligibility),
        "--created-at",
        "2024-03-09T16:33:20Z",
        "--schema-version",
        "p105.source-registry.v1",
        "--fail-on-unreviewed-counting-source",
    ]
    return subprocess.run(command, text=True, capture_output=True, check=False), registry, eligibility


def _source_manifest(tmp_path: Path, *, source_key: str, family: str, reviewed: bool = True) -> Path:
    source_bytes = tmp_path / f"{source_key}.jsonl"
    source_bytes.write_text(json.dumps({"source_key": source_key, "family": family}) + "\n", encoding="utf-8")
    payload = {
        "schema_version": "p105.reviewed-local-source.v1",
        "created_at": "2024-03-09T16:33:20Z",
        "command_argv": ["materialize", source_key],
        "source_key": source_key,
        "source_system": "fixture",
        "source_dataset": source_key,
        "source_family_candidate": family,
        "source_content_hashes": [{"path": str(source_bytes), "sha256": hashlib.sha256(source_bytes.read_bytes()).hexdigest()}],
        "adapter_or_harness": {"name": "fixture", "version": "v1", "command_argv": ["fixture", source_key]},
        "license": {
            "name": "fixture-only",
            "url": "https://example.invalid/license",
            "citation_text": "fixture citation",
            "redistribution_status": "derived-redacted-only",
        },
        "privacy": {
            "review_status": "reviewed-local" if reviewed else "unreviewed",
            "reviewer_id": "p105-reviewer" if reviewed else None,
            "reviewed_at": "2024-03-09T16:33:20Z" if reviewed else None,
            "redaction_status": "reviewed-redacted" if reviewed else "missing",
            "notes": "tiny local fixture",
        },
    }
    path = tmp_path / f"{source_key}-manifest.json"
    _write_json(path, payload)
    return path


def _review_ledger(path: Path, manifests: list[Path], *, approve: bool = True) -> Path:
    decisions = []
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        decisions.append(
            {
                "source_key": manifest["source_key"],
                "reviewer_id": "p105-reviewer",
                "reviewed_at": "2024-03-09T16:33:20Z",
                "decision": "approved" if approve else "rejected",
                "license_decision": "approved" if approve else "rejected",
                "privacy_decision": "approved" if approve else "rejected",
                "family_authority_decision": "approved" if approve else "rejected",
                "source_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                "review_signature_sha256": _json_sha256({"source_key": manifest["source_key"], "decision": approve}),
            }
        )
    return _write_json(path, {"schema_version": "p105.source-review-ledger.v1", "decisions": decisions})


def _require_registry_script() -> None:
    if not REGISTRY_SCRIPT.exists():
        pytest.fail("P105-023/P105-024 RED: missing scripts/build_p105_source_registry.py reviewed registry producer.", pytrace=False)


def test_reviewed_registry_and_eligibility_are_required_before_release_scoring(tmp_path: Path) -> None:
    _require_registry_script()
    approved = _source_manifest(tmp_path, source_key="queue-reviewed", family="queue")
    ledger = _review_ledger(tmp_path / "ledger.json", [approved])

    completed, registry_path, eligibility_path = _run_registry(tmp_path, [approved], ledger)

    assert completed.returncode == 0, completed.stderr
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    eligibility = json.loads(eligibility_path.read_text(encoding="utf-8"))
    assert registry["schema_version"] == "p105.source-registry.v1"
    assert registry["created_at"] == "2024-03-09T16:33:20Z"
    assert registry["command_argv_sha256"] == _json_sha256(registry["command_argv"])
    assert [source["source_key"] for source in registry["sources"]] == ["queue-reviewed"]
    assert eligibility["schema_version"] == "p105.source-eligibility.v1"
    assert eligibility["registry_sha256"] == registry["registry_sha256"]
    assert all(entry["family_authority_source"] == "reviewed_source_registry" for entry in eligibility["entries"])


def test_unreviewed_or_unsupported_sources_are_noncounting_zero_credit(tmp_path: Path) -> None:
    _require_registry_script()
    reviewed = _source_manifest(tmp_path, source_key="deploy-reviewed", family="deploy")
    unreviewed = _source_manifest(tmp_path, source_key="filename-says-database", family="database", reviewed=False)
    unsupported = _source_manifest(tmp_path, source_key="apache-parser-failed", family="unsupported_family")
    ledger = _review_ledger(tmp_path / "ledger.json", [reviewed, unsupported])

    completed, _, eligibility_path = _run_registry(tmp_path, [reviewed, unreviewed, unsupported], ledger)

    assert completed.returncode != 0 or eligibility_path.exists(), completed.stderr
    if eligibility_path.exists():
        entries = json.loads(eligibility_path.read_text(encoding="utf-8"))["entries"]
        noncounting = [entry for entry in entries if entry["source_key"] != "deploy-reviewed"]
        assert noncounting
        for entry in noncounting:
            assert entry["family_candidate"] == "unsupported_family"
            assert entry["eligible_for_release_floor"] is False
            assert entry["unsupported_family_reason"] in {"unreviewed_source", "parser_failed", "predicate_unmapped", "source_insufficient"}
            assert entry.get("counting_rows", 0) == 0
            assert entry.get("counting_coverage_seconds", 0) == 0


def test_missing_command_created_at_hashes_or_reviewer_fields_fail_closed(tmp_path: Path) -> None:
    _require_registry_script()
    manifest = _source_manifest(tmp_path, source_key="queue-missing-provenance", family="queue")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload.pop("command_argv")
    payload["privacy"].pop("reviewer_id")
    _write_json(manifest, payload)
    ledger = _review_ledger(tmp_path / "ledger.json", [manifest])

    completed, _, _ = _run_registry(tmp_path, [manifest], ledger)

    assert completed.returncode != 0
    assert "command_argv" in completed.stderr
    assert "reviewer" in completed.stderr
