from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p174_gcp_provider_lab import (
    ACTION_SCHEMA_VERSION,
    FakeGcpProviderTransport,
    HttpP174ProviderTransport,
    ProviderActionRequest,
    ProviderLab,
    ProviderTransport,
    validate_manifest,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--owner-id", required=True)
    parser.add_argument("--action", choices=("tune_pool", "restart_worker", "rollback_canary"), required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--now", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--transport", choices=("fake", "http"), default="fake")
    parser.add_argument("--action-endpoint", default="http://127.0.0.1:8020")
    parser.add_argument("--evidence-hash", default=None)
    parser.add_argument("--policy-version", default="p174-policy-v1")
    parser.add_argument("--allow-live-lab", action="store_true")
    parser.add_argument("--pool-size", type=int, default=16)
    parser.add_argument("--pause-seconds", type=float, default=0.25)
    parser.add_argument("--receipt-log", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        raw_manifest = _read_json(args.manifest)
        manifest = validate_manifest(raw_manifest)
        if args.dry_run:
            # Dry-run is an execution restriction, not a different reviewed
            # authority document. Preserve the manifest hash so dry-run and
            # live receipts can form one append-only chain.
            manifest = replace(manifest, dry_run=True)
        now = _parse_time(args.now) if args.now else datetime.now(tz=UTC)
        if args.transport == "http" and args.evidence_hash is None:
            raise ValueError("verified_evidence_hash_required_for_live_transport")
        evidence_hash = args.evidence_hash or stable_hash({"manifest_hash": manifest.manifest_hash, "request_id": args.request_id})
        transport: ProviderTransport
        if args.transport == "http":
            if not args.allow_live_lab and not manifest.dry_run:
                raise ValueError("live_lab_acknowledgement_required")
            capability = os.environ.get("P174_ACTION_CAPABILITY", "")
            transport = HttpP174ProviderTransport(
                base_url=args.action_endpoint,
                capability=capability,
                lease_expires_at=now + timedelta(seconds=manifest.lease_ttl_seconds),
            )
            target_state = transport.read(manifest)
            now = _required_observed_at(target_state)
            transport.renew_lease(now + timedelta(seconds=manifest.lease_ttl_seconds))
        else:
            transport = FakeGcpProviderTransport()
        prior_receipts = _read_jsonl(args.receipt_log) if args.receipt_log else []
        lab = ProviderLab(manifest, transport=transport, now=lambda: now, prior_receipts=prior_receipts)
        lab.acquire_lease(args.owner_id, at=now)
        if args.transport == "http":
            if args.receipt_log is None:
                raise ValueError("receipt_log_required_for_live_transport")
            _ensure_appendable(args.receipt_log)
            read_receipt = lab.read_state(args.owner_id)
            _append_jsonl(args.receipt_log, read_receipt)
        parameters: dict[str, Any]
        if args.action == "tune_pool":
            parameters = {"pool_size": args.pool_size}
        elif args.action == "restart_worker":
            parameters = {"pause_seconds": args.pause_seconds}
        else:
            parameters = {"version": "stable"}
        request = ProviderActionRequest(
            schema_version=ACTION_SCHEMA_VERSION,
            request_id=args.request_id,
            idempotency_key=args.request_id,
            project_id=manifest.project_id,
            target_id=manifest.target_id,
            run_id=manifest.run_id,
            action=args.action,
            parameters=parameters,
            evidence_hash=evidence_hash,
            policy_version=args.policy_version,
            created_at=now,
        )
        receipt = lab.run_action(args.owner_id, request)
        if args.receipt_log is not None:
            _append_jsonl(args.receipt_log, receipt)
        print(_json_dumps(receipt))
        return 1 if receipt.get("status") in {"blocked", "rollback_failed"} else 0
    except Exception as exc:
        print(_json_dumps({"status": "blocked", "error": str(exc), "error_type": type(exc).__name__}), file=sys.stderr)
        return 1


def _read_json(path: Path) -> dict[str, Any]:
    return _read_json_text(path.read_text(encoding="utf-8"))


def _required_observed_at(state: Mapping[str, Any]) -> datetime:
    value = state.get("observed_at")
    if not isinstance(value, str):
        raise ValueError("target_observed_at_required")
    return _parse_time(value)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [_read_json_text(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _ensure_appendable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8"):
        pass


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_json_dumps(payload))
        handle.flush()
        os.fsync(handle.fileno())


def _read_json_text(text: str) -> dict[str, Any]:
    value = json.loads(text, object_pairs_hook=_strict_json_object)
    if not isinstance(value, dict):
        raise ValueError("json_object_required")
    return value


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate_json_key:{key}")
        result[key] = value
    return result


def _json_dumps(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str) + "\n"


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


if __name__ == "__main__":
    raise SystemExit(main())
