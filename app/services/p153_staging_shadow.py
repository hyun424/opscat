"""P153 staging read-only shadow observation runtime.

Canonical qualification uses an injected recorded transport. Explicit live
mode uses the same validated profile with a redirect-denying HTTPS GET
transport and environment-variable secret references. No path in this module
can approve or execute a remediation action.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.services.p147_p152_contracts import (
    file_hash,
    load_json,
    stable_hash,
    validate_current_release_bindings,
    with_self_hash,
    write_canonical_json,
)
from app.services.p152_operator_readiness import (
    P152_CONTRACT,
    validate_p152_final_review,
    validate_p152_freeze_manifest,
    validate_p152_release_evidence,
    validate_p152_report,
)
from app.services.redaction import redact_text, redact_value

P153_STATUS = "p153_staging_read_only_shadow_qualified"
P153_RELEASE_STATUS = "p153_staging_shadow_runtime_ready"
P153_CLAIM = "staging_read_only_shadow_runtime_transport_and_investigation_qualified"
P153_LIMITATIONS = (
    "canonical_recorded_transport_not_user_staging_attachment",
    "no_action_approval_or_remediation_authority",
    "no_general_accuracy_or_operator_replacement_claim",
)
P153_SOURCE_PATHS = (
    "app/services/p153_staging_shadow.py",
    "docs/operations/p153-plan-review.md",
    "docs/operations/p153-staging-shadow-plan.md",
    "docs/operations/p153-test-spec.md",
    "docs/tickets/p153/P153-001-contract-red.md",
    "docs/tickets/p153/P153-002-staging-transport.md",
    "docs/tickets/p153/P153-003-evidence-investigator.md",
    "docs/tickets/p153/P153-004-release-verification.md",
    "docs/tickets/p153/README.md",
    "evals/p153/input/staging-shadow-profile.json",
    "scripts/run_p153_staging_shadow.py",
    "scripts/verify_p153.sh",
    "tests/test_p153_staging_shadow.py",
)
P153_PREDECESSOR_PATHS = {
    "report": "evals/p152/output/report.json",
    "freeze_manifest": "evals/p152/output/freeze-manifest.json",
    "final_review": "evals/p152/final-implementation-review.json",
    "release_evidence": "evals/p152/output/release-evidence.json",
}

_PROVIDERS = frozenset({"prometheus", "loki", "sentry"})
_PATH_PREFIXES = {
    "prometheus": ("/api/v1/query", "/api/v1/query_range"),
    "loki": ("/loki/api/v1/query", "/loki/api/v1/query_range"),
}
_SENTRY_PATH_RE = re.compile(
    r"^/api/0/(?:organizations/[A-Za-z0-9._-]+/issues/|"
    r"projects/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+/issues/|"
    r"issues/[A-Za-z0-9._-]+/(?:events/)?|"
    r"events/[A-Za-z0-9._-]+/)$"
)
_HOST_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
_UUID7_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_TIMEOUT_MS = 5_000
_MAX_SOURCES = 10
_MAX_RECORDS = 10_000
_MAX_FOLLOW_UP_READS = 6
_MAX_RETRIES = 2
_LIVE_ACK = "read-only-staging"
_STATE_SCHEMA = "p153.shadow_state.v1"
_REPORT_SCHEMA = "p153.shadow_report.v1"
_FREEZE_SCHEMA = "p153.freeze_manifest.v1"
_REVIEW_SCHEMA = "p153.final_review.v1"
_RELEASE_SCHEMA = "p153.release_evidence.v1"
_UNSAFE_QUERY_KEYS = frozenset({"authorization", "cookie", "password", "secret", "token", "api_key", "apikey", "url", "endpoint", "headers"})


class P153StagingShadowError(ValueError):
    """Raised when P153 cannot preserve its read-only staging boundary."""


@dataclass(frozen=True)
class ReadOnlyResponse:
    status_code: int
    headers: Mapping[str, str]
    body: Any
    elapsed_ms: int = 0


class ReadOnlyTransport(Protocol):
    real_network_call_count: int
    call_count: int

    def get(
        self,
        source: Mapping[str, Any],
        *,
        credential: str | None,
        timeout_ms: int,
        max_response_bytes: int,
    ) -> ReadOnlyResponse:
        """Perform one bounded GET request."""


@dataclass
class RecordedReadOnlyTransport:
    responses: Mapping[str, Sequence[Mapping[str, Any]]]
    call_count: int = 0
    real_network_call_count: int = 0
    _positions: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_profile(cls, profile: Mapping[str, Any]) -> RecordedReadOnlyTransport:
        sources = profile.get("sources", ())
        response_map = {
            str(source.get("source_id")): tuple(
                item for item in _sequence(source.get("recorded_responses")) if isinstance(item, Mapping)
            )
            for source in _sequence(sources)
            if isinstance(source, Mapping)
        }
        return cls(responses=response_map)

    def get(
        self,
        source: Mapping[str, Any],
        *,
        credential: str | None,
        timeout_ms: int,
        max_response_bytes: int,
    ) -> ReadOnlyResponse:
        del credential
        source_id = str(source["source_id"])
        position = self._positions.get(source_id, 0)
        choices = self.responses.get(source_id, ())
        if position >= len(choices):
            raise P153StagingShadowError(f"recorded response exhausted:{source_id}")
        raw = choices[position]
        self._positions[source_id] = position + 1
        self.call_count += 1
        body = deepcopy(raw.get("body"))
        if len(_canonical_bytes(body)) > max_response_bytes:
            raise P153StagingShadowError("response byte budget exceeded")
        return ReadOnlyResponse(
            status_code=_strict_int(raw.get("status_code"), "recorded status"),
            headers={str(key): str(value) for key, value in _mapping(raw.get("headers")).items()},
            body=body,
            elapsed_ms=min(timeout_ms, 25),
        )


class _DenyRedirects(HTTPRedirectHandler):
    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        del req, fp, code, msg, headers, newurl
        return None


@dataclass
class UrllibReadOnlyTransport:
    call_count: int = 0
    real_network_call_count: int = 0

    def get(
        self,
        source: Mapping[str, Any],
        *,
        credential: str | None,
        timeout_ms: int,
        max_response_bytes: int,
    ) -> ReadOnlyResponse:
        query = urlencode({str(key): str(value) for key, value in _mapping(source.get("query")).items()})
        url = f"{source['endpoint']}{source['path']}"
        if query:
            url = f"{url}?{query}"
        headers = {"Accept": "application/json", "User-Agent": "OpsCat-P153-ReadOnly-Shadow/1"}
        if credential:
            headers["Authorization"] = f"Bearer {credential}"
        request = Request(url, headers=headers, method="GET")
        opener = build_opener(_DenyRedirects())
        self.call_count += 1
        self.real_network_call_count += 1
        try:
            with opener.open(request, timeout=timeout_ms / 1000) as response:  # noqa: S310 - exact-host HTTPS profile is validated before transport use
                body = response.read(max_response_bytes + 1)
                if len(body) > max_response_bytes:
                    raise P153StagingShadowError("response byte budget exceeded")
                return ReadOnlyResponse(
                    status_code=int(response.status),
                    headers=dict(response.headers.items()),
                    body=_decode_json(body),
                )
        except HTTPError as exc:
            body = exc.read(max_response_bytes + 1)
            if len(body) > max_response_bytes:
                raise P153StagingShadowError("response byte budget exceeded") from exc
            if 300 <= exc.code < 400:
                raise P153StagingShadowError("redirects are not allowed") from exc
            return ReadOnlyResponse(status_code=exc.code, headers=dict(exc.headers.items()), body=_decode_json(body))
        except (TimeoutError, URLError) as exc:
            raise P153StagingShadowError("staging read-only transport failed") from exc


def load_p153_profile(path: Path) -> dict[str, Any]:
    return _validate_profile(load_json(path), mode="qualification")


def run_p153_shadow_cycle(
    *,
    project_root: Path,
    profile: Mapping[str, Any],
    output_dir: Path,
    transport: ReadOnlyTransport | None = None,
    mode: str = "qualification",
    reset_state: bool = False,
) -> dict[str, Any]:
    validated_profile = _validate_profile(profile, mode=mode)
    if mode == "live" and os.environ.get("OPSCAT_STAGING_SHADOW_ACK") != _LIVE_ACK:
        raise P153StagingShadowError("live staging acknowledgement missing")
    predecessor = _validate_p152_predecessor(project_root)
    profile_hash = stable_hash(_profile_projection(validated_profile))
    state_path = output_dir / "shadow-state.json"
    if reset_state and state_path.exists():
        state_path.unlink()
    previous_state = _load_state(state_path, profile_hash=profile_hash)
    active_transport = transport or (UrllibReadOnlyTransport() if mode == "live" else RecordedReadOnlyTransport.from_profile(validated_profile))
    evidence: list[dict[str, Any]] = []
    source_results: list[dict[str, Any]] = []
    retry_count = 0
    redaction_count = 0

    limits = validated_profile["limits"]
    for source in validated_profile["sources"]:
        credential = _resolve_credential(source, mode=mode)
        response, attempts = _read_with_retry(
            active_transport,
            source,
            credential=credential,
            timeout_ms=limits["timeout_ms"],
            max_response_bytes=limits["max_response_bytes"],
            max_retries=limits["max_retries_per_source"],
        )
        retry_count += attempts - 1
        if response is None:
            source_results.append(
                {
                    "source_id": source["source_id"],
                    "provider": source["provider"],
                    "status": "unavailable",
                    "attempt_count": attempts,
                    "record_count": 0,
                    "credential_ref_fingerprint": _fingerprint(source["credential_env"]),
                }
            )
            continue
        records, source_redactions = _normalize_response(source, response, max_records=limits["max_records_per_source"])
        redaction_count += source_redactions
        evidence.extend(records)
        source_results.append(
            {
                "source_id": source["source_id"],
                "provider": source["provider"],
                "status": "successful",
                "attempt_count": attempts,
                "record_count": len(records),
                "credential_ref_fingerprint": _fingerprint(source["credential_env"]),
            }
        )

    evidence = sorted(evidence, key=lambda item: (str(item["provider"]), str(item["timestamp"]), str(item["evidence_hash"])))
    previous_hashes = set(previous_state["evidence_hashes"]) if previous_state is not None else set()
    new_evidence = [item for item in evidence if item["evidence_hash"] not in previous_hashes]
    duplicate_count = len(evidence) - len(new_evidence)
    judgment = _investigate(evidence, successful_providers={item["provider"] for item in source_results if item["status"] == "successful"}, max_follow_up_reads=limits["max_follow_up_reads"])
    new_state = _build_state(previous_state, profile_hash=profile_hash, evidence=evidence)
    _write_state(state_path, new_state)
    audit = {
        "transport_call_count": active_transport.call_count,
        "real_network_call_count": active_transport.real_network_call_count,
        "retry_count": retry_count,
        "follow_up_read_count": len(judgment["evidence_requests"]),
        "redaction_count": redaction_count,
        "external_model_call_count": 0,
        "write_request_count": 0,
        "secret_persistence_count": 0,
        "approval_count": 0,
        "action_execution_count": 0,
        "production_mutation_count": 0,
    }
    summary = {
        "source_count": len(validated_profile["sources"]),
        "successful_source_count": sum(1 for item in source_results if item["status"] == "successful"),
        "normalized_evidence_count": len(evidence),
        "new_evidence_count": len(new_evidence),
        "duplicate_evidence_count": duplicate_count,
        "supporting_provider_count": judgment["supporting_provider_count"],
        "resume_count": 1 if previous_state is not None else 0,
    }
    report = {
        "schema_version": _REPORT_SCHEMA,
        "phase": "p153",
        "status": P153_STATUS,
        "claim": P153_CLAIM,
        "limitations": list(P153_LIMITATIONS),
        "mode": mode,
        "profile_hash": profile_hash,
        "predecessor": predecessor,
        "source_hashes": _current_source_hashes(project_root),
        "summary": summary,
        "sources": source_results,
        "evidence": evidence,
        "judgment": judgment,
        "audit": audit,
        "state_hash": new_state["state_hash"],
        "report_hash": "",
    }
    validated = validate_p153_report(with_self_hash(report, "report_hash"))
    write_canonical_json(output_dir / "report.json", validated)
    return validated


def validate_p153_report(report: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(report))
    expected_keys = {
        "schema_version",
        "phase",
        "status",
        "claim",
        "limitations",
        "mode",
        "profile_hash",
        "predecessor",
        "source_hashes",
        "summary",
        "sources",
        "evidence",
        "judgment",
        "audit",
        "state_hash",
        "report_hash",
    }
    if set(value) != expected_keys or value.get("schema_version") != _REPORT_SCHEMA or value.get("phase") != "p153":
        raise P153StagingShadowError("report schema invalid")
    if value.get("status") != P153_STATUS or value.get("claim") != P153_CLAIM or value.get("limitations") != list(P153_LIMITATIONS):
        raise P153StagingShadowError("report claim invalid")
    if value.get("mode") not in {"qualification", "live"}:
        raise P153StagingShadowError("report mode invalid")
    _require_hash(value.get("profile_hash"), "profile hash")
    _require_hash(value.get("state_hash"), "state hash")
    if set(_mapping(value.get("source_hashes"))) != set(P153_SOURCE_PATHS):
        raise P153StagingShadowError("report source hash keyset invalid")
    for item in _mapping(value.get("source_hashes")).values():
        _require_hash(item, "source hash")
    summary = _mapping(value.get("summary"))
    _validate_summary(summary)
    audit = _mapping(value.get("audit"))
    _validate_audit(audit, require_real_network_zero=value["mode"] == "qualification")
    if value["mode"] == "qualification" and audit["real_network_call_count"] != 0:
        raise P153StagingShadowError("qualification real network counter must be zero")
    sources = value.get("sources")
    evidence = value.get("evidence")
    if not isinstance(sources, list) or not isinstance(evidence, list):
        raise P153StagingShadowError("report source or evidence list invalid")
    if summary["source_count"] != len(sources) or summary["normalized_evidence_count"] != len(evidence):
        raise P153StagingShadowError("report denominator invalid")
    if summary["successful_source_count"] > summary["source_count"]:
        raise P153StagingShadowError("report successful source denominator invalid")
    if summary["new_evidence_count"] + summary["duplicate_evidence_count"] != summary["normalized_evidence_count"]:
        raise P153StagingShadowError("report evidence denominator invalid")
    for record in evidence:
        _validate_evidence(record)
    judgment = _mapping(value.get("judgment"))
    _validate_judgment(judgment)
    evidence_hashes = {str(record["evidence_hash"]) for record in evidence}
    referenced_hashes = set(_sequence(judgment.get("citations")))
    for hypothesis in _sequence(judgment.get("hypotheses")):
        if isinstance(hypothesis, Mapping):
            referenced_hashes.update(str(item) for item in _sequence(hypothesis.get("supporting_citations")))
            referenced_hashes.update(str(item) for item in _sequence(hypothesis.get("contradicting_citations")))
    if not referenced_hashes.issubset(evidence_hashes):
        raise P153StagingShadowError("judgment citation binding invalid")
    _validate_predecessor_shape(_mapping(value.get("predecessor")))
    _validate_self_hash(value, "report_hash")
    return value


def build_p153_freeze_manifest(*, project_root: Path, report: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_p153_report(report)
    source_hashes = _current_source_hashes(project_root)
    if validated["source_hashes"] != source_hashes:
        raise P153StagingShadowError("freeze source hashes stale")
    predecessor = _validate_p152_predecessor(project_root)
    if validated["predecessor"] != predecessor:
        raise P153StagingShadowError("freeze predecessor stale")
    manifest = {
        "schema_version": _FREEZE_SCHEMA,
        "phase": "p153",
        "plan_hash": source_hashes["docs/operations/p153-staging-shadow-plan.md"],
        "test_spec_hash": source_hashes["docs/operations/p153-test-spec.md"],
        "profile_hash": validated["profile_hash"],
        "predecessor_hash": predecessor["evidence_hash"],
        "source_hashes": source_hashes,
        "report_hash": validated["report_hash"],
        "manifest_hash": "",
    }
    return validate_p153_freeze_manifest(with_self_hash(manifest, "manifest_hash"))


def validate_p153_freeze_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(manifest))
    if set(value) != {
        "schema_version",
        "phase",
        "plan_hash",
        "test_spec_hash",
        "profile_hash",
        "predecessor_hash",
        "source_hashes",
        "report_hash",
        "manifest_hash",
    } or value.get("schema_version") != _FREEZE_SCHEMA or value.get("phase") != "p153":
        raise P153StagingShadowError("freeze manifest schema invalid")
    for key in ("plan_hash", "test_spec_hash", "profile_hash", "predecessor_hash", "report_hash", "manifest_hash"):
        _require_hash(value.get(key), key)
    if set(_mapping(value.get("source_hashes"))) != set(P153_SOURCE_PATHS):
        raise P153StagingShadowError("freeze source hashes invalid")
    for item in _mapping(value.get("source_hashes")).values():
        _require_hash(item, "freeze source hash")
    if value["plan_hash"] != value["source_hashes"]["docs/operations/p153-staging-shadow-plan.md"]:
        raise P153StagingShadowError("freeze plan binding invalid")
    if value["test_spec_hash"] != value["source_hashes"]["docs/operations/p153-test-spec.md"]:
        raise P153StagingShadowError("freeze test specification binding invalid")
    _validate_self_hash(value, "manifest_hash")
    return value


def build_p153_final_review(
    *,
    report: Mapping[str, Any],
    freeze_manifest: Mapping[str, Any],
    writer_agent_id: str,
    reviewer_agent_id: str,
    reviewer_identity: str,
    reviewed_at: str,
) -> dict[str, Any]:
    review = {
        "schema_version": _REVIEW_SCHEMA,
        "phase": "p153",
        "writer_agent_id": writer_agent_id,
        "reviewer_agent_id": reviewer_agent_id,
        "reviewer_identity": reviewer_identity,
        "reviewed_at": reviewed_at,
        "decision": "approve",
        "findings": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
        "limitations": list(P153_LIMITATIONS),
        "reviewed_report_hash": validate_p153_report(report)["report_hash"],
        "reviewed_manifest_hash": validate_p153_freeze_manifest(freeze_manifest)["manifest_hash"],
        "review_hash": "",
    }
    return validate_p153_final_review(with_self_hash(review, "review_hash"), report=report, freeze_manifest=freeze_manifest)


def validate_p153_final_review(
    review: Mapping[str, Any],
    *,
    report: Mapping[str, Any] | None = None,
    freeze_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    value = deepcopy(dict(review))
    if set(value) != {
        "schema_version",
        "phase",
        "writer_agent_id",
        "reviewer_agent_id",
        "reviewer_identity",
        "reviewed_at",
        "decision",
        "findings",
        "limitations",
        "reviewed_report_hash",
        "reviewed_manifest_hash",
        "review_hash",
    } or value.get("schema_version") != _REVIEW_SCHEMA or value.get("phase") != "p153":
        raise P153StagingShadowError("review schema invalid")
    if value.get("decision") != "approve" or value.get("limitations") != list(P153_LIMITATIONS):
        raise P153StagingShadowError("review decision invalid")
    writer = str(value.get("writer_agent_id", ""))
    reviewer = str(value.get("reviewer_agent_id", ""))
    if not _UUID7_RE.fullmatch(writer) or not _UUID7_RE.fullmatch(reviewer) or writer == reviewer:
        raise P153StagingShadowError("review writer separation invalid")
    if not isinstance(value.get("reviewer_identity"), str) or not value["reviewer_identity"]:
        raise P153StagingShadowError("review identity invalid")
    reviewed_at = str(value.get("reviewed_at", ""))
    if not reviewed_at.endswith("Z"):
        raise P153StagingShadowError("review timestamp must be UTC")
    try:
        datetime.fromisoformat(reviewed_at.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as exc:
        raise P153StagingShadowError("review timestamp invalid") from exc
    findings = _mapping(value.get("findings"))
    if set(findings) != {"p0", "p1", "p2", "p3"} or any(findings[key] != 0 for key in findings):
        raise P153StagingShadowError("review findings must be zero")
    if report is not None and value.get("reviewed_report_hash") != validate_p153_report(report)["report_hash"]:
        raise P153StagingShadowError("review report binding invalid")
    if freeze_manifest is not None and value.get("reviewed_manifest_hash") != validate_p153_freeze_manifest(freeze_manifest)["manifest_hash"]:
        raise P153StagingShadowError("review manifest binding invalid")
    _validate_self_hash(value, "review_hash")
    return value


def assemble_p153_release_evidence(
    *,
    report: Mapping[str, Any],
    freeze_manifest: Mapping[str, Any],
    final_review: Mapping[str, Any],
) -> dict[str, Any]:
    validated_report = validate_p153_report(report)
    validated_freeze = validate_p153_freeze_manifest(freeze_manifest)
    validated_review = validate_p153_final_review(final_review, report=validated_report, freeze_manifest=validated_freeze)
    if validated_freeze["report_hash"] != validated_report["report_hash"]:
        raise P153StagingShadowError("release report freeze mismatch")
    evidence = {
        "schema_version": _RELEASE_SCHEMA,
        "phase": "p153",
        "release_status": P153_RELEASE_STATUS,
        "claim": P153_CLAIM,
        "limitations": list(P153_LIMITATIONS),
        "report_hash": validated_report["report_hash"],
        "freeze_hash": validated_freeze["manifest_hash"],
        "review_hash": validated_review["review_hash"],
        "predecessor": validated_report["predecessor"],
        "source_hashes": validated_report["source_hashes"],
        "summary": validated_report["summary"],
        "judgment": validated_report["judgment"],
        "audit": validated_report["audit"],
        "evidence_hash": "",
    }
    return _validate_release_shape(with_self_hash(evidence, "evidence_hash"))


def validate_p153_release_evidence(evidence: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    value = _validate_release_shape(evidence)
    if value["source_hashes"] != _current_source_hashes(project_root):
        raise P153StagingShadowError("release source bindings stale")
    if value["predecessor"] != _validate_p152_predecessor(project_root):
        raise P153StagingShadowError("release predecessor binding stale")
    report_path = project_root / "evals/p153/output/report.json"
    freeze_path = project_root / "evals/p153/output/freeze-manifest.json"
    review_path = project_root / "evals/p153/final-implementation-review.json"
    report = validate_p153_report(load_json(report_path)) if report_path.exists() else None
    if report is not None and value["report_hash"] != report["report_hash"]:
        raise P153StagingShadowError("release canonical report binding invalid")
    if report is not None and freeze_path.exists() and review_path.exists():
        freeze = validate_p153_freeze_manifest(load_json(freeze_path))
        review = validate_p153_final_review(load_json(review_path), report=report, freeze_manifest=freeze)
        if value["freeze_hash"] != freeze["manifest_hash"] or value["review_hash"] != review["review_hash"]:
            raise P153StagingShadowError("release canonical companion binding invalid")
    return value


def _validate_release_shape(evidence: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(evidence))
    if set(value) != {
        "schema_version",
        "phase",
        "release_status",
        "claim",
        "limitations",
        "report_hash",
        "freeze_hash",
        "review_hash",
        "predecessor",
        "source_hashes",
        "summary",
        "judgment",
        "audit",
        "evidence_hash",
    } or value.get("schema_version") != _RELEASE_SCHEMA or value.get("phase") != "p153":
        raise P153StagingShadowError("release schema invalid")
    if value.get("release_status") != P153_RELEASE_STATUS or value.get("claim") != P153_CLAIM or value.get("limitations") != list(P153_LIMITATIONS):
        raise P153StagingShadowError("release claim invalid")
    for key in ("report_hash", "freeze_hash", "review_hash", "evidence_hash"):
        _require_hash(value.get(key), key)
    if set(_mapping(value.get("source_hashes"))) != set(P153_SOURCE_PATHS):
        raise P153StagingShadowError("release source hash keyset invalid")
    for item in _mapping(value.get("source_hashes")).values():
        _require_hash(item, "release source hash")
    _validate_predecessor_shape(_mapping(value.get("predecessor")))
    _validate_summary(_mapping(value.get("summary")))
    _validate_judgment(_mapping(value.get("judgment")))
    audit = _mapping(value.get("audit"))
    _validate_audit(audit, require_real_network_zero=True)
    _validate_self_hash(value, "evidence_hash")
    return value


def _validate_profile(profile: Mapping[str, Any], *, mode: str) -> dict[str, Any]:
    value = deepcopy(dict(profile))
    if value.get("schema_version") != "p153.staging_shadow_profile.v1" or value.get("environment") != "staging":
        raise P153StagingShadowError("profile must target staging")
    if mode not in {"qualification", "live"}:
        raise P153StagingShadowError("mode invalid")
    allowed_hosts = value.get("allowed_hosts")
    sources = value.get("sources")
    limits = _mapping(value.get("limits"))
    if (
        not isinstance(allowed_hosts, list)
        or not allowed_hosts
        or not all(isinstance(item, str) and _HOST_RE.fullmatch(item) for item in allowed_hosts)
    ):
        raise P153StagingShadowError("allowed host list invalid")
    if len(allowed_hosts) != len(set(allowed_hosts)):
        raise P153StagingShadowError("allowed hosts duplicated")
    if not isinstance(sources, list) or not sources:
        raise P153StagingShadowError("profile sources missing")
    validated_limits = {
        "max_sources": _bounded_int(limits.get("max_sources"), 1, _MAX_SOURCES, "source budget"),
        "max_follow_up_reads": _bounded_int(limits.get("max_follow_up_reads"), 0, _MAX_FOLLOW_UP_READS, "follow-up budget"),
        "max_retries_per_source": _bounded_int(limits.get("max_retries_per_source"), 0, _MAX_RETRIES, "retry budget"),
        "max_response_bytes": _bounded_int(limits.get("max_response_bytes"), 1_024, _MAX_RESPONSE_BYTES, "response budget"),
        "max_records_per_source": _bounded_int(limits.get("max_records_per_source"), 1, _MAX_RECORDS, "record budget"),
        "timeout_ms": _bounded_int(limits.get("timeout_ms"), 100, _MAX_TIMEOUT_MS, "timeout budget"),
    }
    if len(sources) > validated_limits["max_sources"]:
        raise P153StagingShadowError("source budget exceeded")
    validated_sources = [_validate_source(item, allowed_hosts=allowed_hosts, mode=mode) for item in sources]
    source_ids = [item["source_id"] for item in validated_sources]
    if len(source_ids) != len(set(source_ids)):
        raise P153StagingShadowError("source id duplicated")
    return {
        "schema_version": "p153.staging_shadow_profile.v1",
        "environment": "staging",
        "allowed_hosts": sorted(allowed_hosts),
        "limits": validated_limits,
        "sources": validated_sources,
    }


def _validate_source(raw: Any, *, allowed_hosts: Sequence[str], mode: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise P153StagingShadowError("source must be an object")
    source = deepcopy(dict(raw))
    provider = str(source.get("provider", "")).lower()
    source_id = str(source.get("source_id", ""))
    endpoint = str(source.get("endpoint", "")).rstrip("/")
    method = str(source.get("method", "")).upper()
    path = str(source.get("path", ""))
    credential_env = str(source.get("credential_env", ""))
    if provider not in _PROVIDERS or not source_id:
        raise P153StagingShadowError("unknown provider or source")
    if method != "GET":
        raise P153StagingShadowError("only GET is allowed")
    parsed = urlparse(endpoint)
    try:
        port = parsed.port
    except ValueError as exc:
        raise P153StagingShadowError("source host is not allowlisted") from exc
    if mode == "live" and parsed.scheme != "https":
        raise P153StagingShadowError("live staging requires HTTPS")
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.hostname not in set(allowed_hosts)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or port not in {None, 443 if parsed.scheme == "https" else 80}
    ):
        raise P153StagingShadowError("source host is not allowlisted")
    if not _provider_path_allowed(provider, path):
        raise P153StagingShadowError("provider path is not allowlisted")
    if credential_env and _ENV_NAME_RE.fullmatch(credential_env) is None:
        raise P153StagingShadowError("credential must be an environment variable name")
    query = _mapping(source.get("query"))
    if any(str(key).lower() in _UNSAFE_QUERY_KEYS for key in query):
        raise P153StagingShadowError("unsafe query field")
    for key, item in query.items():
        if not isinstance(key, str) or not isinstance(item, (str, int, float)) or isinstance(item, bool) or len(str(item)) > 4_096:
            raise P153StagingShadowError("query value invalid")
    recorded = [deepcopy(dict(item)) for item in _sequence(source.get("recorded_responses")) if isinstance(item, Mapping)]
    if mode == "qualification" and not recorded:
        raise P153StagingShadowError("qualification source requires recorded responses")
    return {
        "source_id": source_id,
        "provider": provider,
        "method": "GET",
        "endpoint": endpoint,
        "path": path,
        "credential_env": credential_env,
        "query": dict(sorted((str(key), item) for key, item in query.items())),
        "recorded_responses": recorded,
    }


def _path_matches_prefix(path: str, prefix: str) -> bool:
    return path == prefix


def _provider_path_allowed(provider: str, path: str) -> bool:
    if provider == "sentry":
        return _SENTRY_PATH_RE.fullmatch(path) is not None
    return any(_path_matches_prefix(path, prefix) for prefix in _PATH_PREFIXES[provider])


def _read_with_retry(
    transport: ReadOnlyTransport,
    source: Mapping[str, Any],
    *,
    credential: str | None,
    timeout_ms: int,
    max_response_bytes: int,
    max_retries: int,
) -> tuple[ReadOnlyResponse | None, int]:
    attempts = 0
    while attempts <= max_retries:
        attempts += 1
        response = transport.get(
            source,
            credential=credential,
            timeout_ms=timeout_ms,
            max_response_bytes=max_response_bytes,
        )
        if response.status_code == 200:
            return response, attempts
        if response.status_code != 429 and response.status_code < 500:
            return None, attempts
    return None, attempts


def _normalize_response(source: Mapping[str, Any], response: ReadOnlyResponse, *, max_records: int) -> tuple[list[dict[str, Any]], int]:
    provider = str(source["provider"])
    if provider == "prometheus":
        return _normalize_prometheus(source, response.body, max_records=max_records)
    if provider == "loki":
        return _normalize_loki(source, response.body, max_records=max_records)
    return _normalize_sentry(source, response.body, max_records=max_records)


def _normalize_prometheus(source: Mapping[str, Any], body: Any, *, max_records: int) -> tuple[list[dict[str, Any]], int]:
    data = _mapping(_mapping(body).get("data"))
    result = _sequence(data.get("result"))
    records: list[dict[str, Any]] = []
    redactions = 0
    for series in result:
        if not isinstance(series, Mapping):
            continue
        labels, label_redactions = _safe_labels(_mapping(series.get("metric")))
        redactions += label_redactions
        for sample in list(_sequence(series.get("values")))[:max_records]:
            if not isinstance(sample, Sequence) or isinstance(sample, (str, bytes)) or len(sample) < 2:
                continue
            try:
                value = float(sample[1])
            except (TypeError, ValueError):
                continue
            severity = "critical" if value >= 0.1 else "info"
            records.append(
                _evidence_record(
                    provider="prometheus",
                    source_id=str(source["source_id"]),
                    timestamp=str(sample[0]),
                    service=labels.get("service", "unknown"),
                    signal_kind=labels.get("signal", "metric"),
                    severity=severity,
                    summary=f"metric value={value:.6f}",
                    labels=labels,
                )
            )
            if len(records) >= max_records:
                return records, redactions
    return records, redactions


def _normalize_loki(source: Mapping[str, Any], body: Any, *, max_records: int) -> tuple[list[dict[str, Any]], int]:
    result = _sequence(_mapping(_mapping(body).get("data")).get("result"))
    records: list[dict[str, Any]] = []
    redactions = 0
    for stream in result:
        if not isinstance(stream, Mapping):
            continue
        labels, label_redactions = _safe_labels(_mapping(stream.get("stream")))
        redactions += label_redactions
        for pair in _sequence(stream.get("values")):
            if not isinstance(pair, Sequence) or isinstance(pair, (str, bytes)) or len(pair) < 2:
                continue
            raw_summary = str(pair[1])
            safe_summary = redact_text(raw_summary)
            redactions += int(safe_summary != raw_summary)
            records.append(
                _evidence_record(
                    provider="loki",
                    source_id=str(source["source_id"]),
                    timestamp=str(pair[0]),
                    service=labels.get("service", "unknown"),
                    signal_kind="log",
                    severity=labels.get("level", "unknown"),
                    summary=safe_summary,
                    labels=labels,
                )
            )
            if len(records) >= max_records:
                return records, redactions
    return records, redactions


def _normalize_sentry(source: Mapping[str, Any], body: Any, *, max_records: int) -> tuple[list[dict[str, Any]], int]:
    issues = _sequence(body)
    records: list[dict[str, Any]] = []
    redactions = 0
    for issue in issues[:max_records]:
        if not isinstance(issue, Mapping):
            continue
        safe_issue = redact_value(issue)
        redactions += int(safe_issue != issue)
        safe = _mapping(safe_issue)
        project = _mapping(safe.get("project"))
        metadata = _mapping(safe.get("metadata"))
        labels = {
            "release": str(metadata.get("release", "")),
            "issue_id": str(safe.get("id", "")),
            "count": str(safe.get("count", "0")),
        }
        records.append(
            _evidence_record(
                provider="sentry",
                source_id=str(source["source_id"]),
                timestamp=str(safe.get("lastSeen", "")),
                service=str(project.get("slug", "unknown")),
                signal_kind="error",
                severity=str(safe.get("level", "error")),
                summary=redact_text(str(safe.get("title", ""))),
                labels=labels,
            )
        )
    return records, redactions


def _evidence_record(
    *,
    provider: str,
    source_id: str,
    timestamp: str,
    service: str,
    signal_kind: str,
    severity: str,
    summary: str,
    labels: Mapping[str, str],
) -> dict[str, Any]:
    body = {
        "schema_version": "p153.normalized_evidence.v1",
        "provider": provider,
        "source_id": source_id,
        "timestamp": timestamp,
        "service": service,
        "signal_kind": signal_kind,
        "severity": severity,
        "summary": summary,
        "labels": dict(sorted(labels.items())),
    }
    return {**body, "evidence_hash": stable_hash(body)}


def _safe_labels(value: Mapping[str, Any]) -> tuple[dict[str, str], int]:
    safe_value = _mapping(redact_value(value))
    return (
        {str(key): str(item) for key, item in safe_value.items()},
        int(dict(safe_value) != dict(value)),
    )


def _investigate(
    evidence: Sequence[Mapping[str, Any]],
    *,
    successful_providers: set[str],
    max_follow_up_reads: int,
) -> dict[str, Any]:
    providers = {str(item.get("provider")) for item in evidence}
    summaries = " ".join(str(item.get("summary", "")).lower() for item in evidence)
    releases_by_provider = {
        str(item.get("provider")): str(_mapping(item.get("labels")).get("release", ""))
        for item in evidence
        if str(_mapping(item.get("labels")).get("release", ""))
    }
    release_counts: dict[str, set[str]] = {}
    for provider, release in releases_by_provider.items():
        release_counts.setdefault(release, set()).add(provider)
    common_release = next((release for release, release_providers in release_counts.items() if len(release_providers) >= 2), "")
    high_metric = any(item.get("provider") == "prometheus" and item.get("severity") == "critical" for item in evidence)
    timeout = "timeout" in summaries
    pool_wait = "pool wait" in summaries

    hypotheses = [
        _hypothesis(
            "recent_deploy_regression",
            supports=[
                item["evidence_hash"]
                for item in evidence
                if common_release and _mapping(item.get("labels")).get("release") == common_release
            ],
            contradictions=[],
            score_bps=9200 if common_release and high_metric and timeout else 3000,
        ),
        _hypothesis(
            "dependency_timeout",
            supports=[item["evidence_hash"] for item in evidence if "timeout" in str(item.get("summary", "")).lower()],
            contradictions=[],
            score_bps=7600 if timeout and len(providers) >= 2 else 2500,
        ),
        _hypothesis(
            "resource_saturation",
            supports=[item["evidence_hash"] for item in evidence if "pool wait" in str(item.get("summary", "")).lower()],
            contradictions=[],
            score_bps=5200 if pool_wait else 1000,
        ),
    ]
    hypotheses.sort(key=lambda item: (-int(item["score_bps"]), str(item["hypothesis"])))
    missing = [provider for provider in sorted(_PROVIDERS) if provider not in successful_providers]
    requests = [
        {
            "provider": provider,
            "capability": "read_only_follow_up",
            "reason": f"missing independent {provider} evidence",
        }
        for provider in missing[:max_follow_up_reads]
    ]
    top = hypotheses[0]
    supporting_providers = {
        str(item["provider"])
        for item in evidence
        if item["evidence_hash"] in set(top["supporting_citations"])
    }
    enough = len(supporting_providers) >= 2 and len(top["supporting_citations"]) >= 3 and int(top["score_bps"]) >= 7_000
    return {
        "schema_version": "p153.shadow_judgment.v1",
        "outcome": "incident_likely" if enough else "insufficient_evidence",
        "top_hypothesis": str(top["hypothesis"]) if enough else None,
        "confidence_bps": int(top["score_bps"]) if enough else 0,
        "supporting_provider_count": len(supporting_providers) if enough else len(providers),
        "citations": list(top["supporting_citations"]) if enough else [],
        "hypotheses": hypotheses,
        "evidence_requests": requests,
        "proposed_response": ["inspect_deploy_diff", "prepare_reversible_rollback_candidate"] if enough else [],
        "execution": "shadow_only_no_action",
    }


def _hypothesis(name: str, *, supports: Sequence[str], contradictions: Sequence[str], score_bps: int) -> dict[str, Any]:
    return {
        "hypothesis": name,
        "score_bps": score_bps,
        "supporting_citations": sorted(set(supports)),
        "contradicting_citations": sorted(set(contradictions)),
    }


def _load_state(path: Path, *, profile_hash: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        state = load_json(path)
        if set(state) != {"schema_version", "generation", "profile_hash", "evidence_hashes", "cursors", "parent_hash", "state_hash"}:
            raise P153StagingShadowError("state schema invalid")
        if state.get("schema_version") != _STATE_SCHEMA or state.get("profile_hash") != profile_hash:
            raise P153StagingShadowError("state profile invalid")
        if isinstance(state.get("generation"), bool) or not isinstance(state.get("generation"), int) or state["generation"] < 1:
            raise P153StagingShadowError("state generation invalid")
        hashes = state.get("evidence_hashes")
        if not isinstance(hashes, list) or hashes != sorted(set(hashes)) or any(not _HASH_RE.fullmatch(str(item)) for item in hashes):
            raise P153StagingShadowError("state evidence hashes invalid")
        _validate_self_hash(state, "state_hash")
        return state
    except (OSError, ValueError, TypeError) as exc:
        if isinstance(exc, P153StagingShadowError):
            raise
        raise P153StagingShadowError("state validation failed") from exc


def _build_state(previous: Mapping[str, Any] | None, *, profile_hash: str, evidence: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    previous_hashes = set(_sequence(previous.get("evidence_hashes"))) if previous else set()
    all_hashes = sorted(previous_hashes | {str(item["evidence_hash"]) for item in evidence})
    cursors: dict[str, str] = dict(_mapping(previous.get("cursors"))) if previous else {}
    for item in evidence:
        source_id = str(item["source_id"])
        timestamp = str(item["timestamp"])
        if timestamp > cursors.get(source_id, ""):
            cursors[source_id] = timestamp
    state = {
        "schema_version": _STATE_SCHEMA,
        "generation": int(previous["generation"]) + 1 if previous else 1,
        "profile_hash": profile_hash,
        "evidence_hashes": all_hashes,
        "cursors": dict(sorted(cursors.items())),
        "parent_hash": str(previous["state_hash"]) if previous else "sha256:" + "0" * 64,
        "state_hash": "",
    }
    return with_self_hash(state, "state_hash")


def _write_state(path: Path, state: Mapping[str, Any]) -> None:
    write_canonical_json(path, state)


def _validate_p152_predecessor(project_root: Path) -> dict[str, Any]:
    report = validate_p152_report(load_json(project_root / P153_PREDECESSOR_PATHS["report"]))
    validate_current_release_bindings(project_root, report, P152_CONTRACT, require_companion_artifacts=True)
    freeze = validate_p152_freeze_manifest(load_json(project_root / P153_PREDECESSOR_PATHS["freeze_manifest"]))
    review = validate_p152_final_review(
        load_json(project_root / P153_PREDECESSOR_PATHS["final_review"]),
        report=report,
        freeze_manifest=freeze,
    )
    release = validate_p152_release_evidence(load_json(project_root / P153_PREDECESSOR_PATHS["release_evidence"]))
    expected = {
        "report_hash": report["report_hash"],
        "freeze_hash": freeze["manifest_hash"],
        "review_hash": review["review_hash"],
    }
    for key, required in expected.items():
        if release.get(key) != required:
            raise P153StagingShadowError(f"P152 predecessor companion mismatch:{key}")
    return {
        "phase": "p152",
        "schema_version": str(release["schema_version"]),
        "required_status": str(release["status"]),
        "evidence_hash": str(release["evidence_hash"]),
        "artifact_hashes": {
            key: file_hash(project_root / relative)
            for key, relative in sorted(P153_PREDECESSOR_PATHS.items())
        },
    }


def _validate_predecessor_shape(value: Mapping[str, Any]) -> None:
    if set(value) != {"phase", "schema_version", "required_status", "evidence_hash", "artifact_hashes"}:
        raise P153StagingShadowError("predecessor schema invalid")
    if value.get("phase") != "p152" or value.get("schema_version") != "p152.release_evidence.v1" or value.get("required_status") != "p152_bounded_operator_agent_qualified":
        raise P153StagingShadowError("predecessor identity invalid")
    _require_hash(value.get("evidence_hash"), "predecessor evidence hash")
    if set(_mapping(value.get("artifact_hashes"))) != set(P153_PREDECESSOR_PATHS):
        raise P153StagingShadowError("predecessor artifact hash keyset invalid")
    for item in _mapping(value.get("artifact_hashes")).values():
        _require_hash(item, "predecessor artifact hash")


def _current_source_hashes(project_root: Path) -> dict[str, str]:
    return {path: file_hash(project_root / path) for path in sorted(P153_SOURCE_PATHS)}


def _profile_projection(profile: Mapping[str, Any]) -> dict[str, Any]:
    projected = deepcopy(dict(profile))
    for source in projected["sources"]:
        source.pop("recorded_responses", None)
    return projected


def _resolve_credential(source: Mapping[str, Any], *, mode: str) -> str | None:
    name = str(source.get("credential_env", ""))
    if mode != "live" or not name:
        return None
    value = os.environ.get(name)
    if not value:
        raise P153StagingShadowError(f"live credential environment variable missing:{name}")
    return value


def _validate_evidence(record: Any) -> None:
    if not isinstance(record, Mapping) or set(record) != {
        "schema_version",
        "provider",
        "source_id",
        "timestamp",
        "service",
        "signal_kind",
        "severity",
        "summary",
        "labels",
        "evidence_hash",
    }:
        raise P153StagingShadowError("evidence schema invalid")
    if record.get("schema_version") != "p153.normalized_evidence.v1" or record.get("provider") not in _PROVIDERS:
        raise P153StagingShadowError("evidence identity invalid")
    for key in ("source_id", "timestamp", "service", "signal_kind", "severity", "summary"):
        if not isinstance(record.get(key), str):
            raise P153StagingShadowError(f"evidence field invalid:{key}")
    labels = record.get("labels")
    if not isinstance(labels, Mapping) or not all(isinstance(key, str) and isinstance(item, str) for key, item in labels.items()):
        raise P153StagingShadowError("evidence labels invalid")
    _validate_self_hash(record, "evidence_hash")


def _validate_judgment(judgment: Mapping[str, Any]) -> None:
    if set(judgment) != {
        "schema_version",
        "outcome",
        "top_hypothesis",
        "confidence_bps",
        "supporting_provider_count",
        "citations",
        "hypotheses",
        "evidence_requests",
        "proposed_response",
        "execution",
    } or judgment.get("schema_version") != "p153.shadow_judgment.v1":
        raise P153StagingShadowError("judgment schema invalid")
    if judgment.get("outcome") not in {"incident_likely", "insufficient_evidence"} or judgment.get("execution") != "shadow_only_no_action":
        raise P153StagingShadowError("judgment boundary invalid")
    if judgment["outcome"] == "insufficient_evidence" and (judgment.get("top_hypothesis") is not None or judgment.get("citations")):
        raise P153StagingShadowError("abstention semantics invalid")
    if judgment["outcome"] == "incident_likely" and (
        not isinstance(judgment.get("top_hypothesis"), str)
        or not isinstance(judgment.get("confidence_bps"), int)
        or judgment["confidence_bps"] < 7_000
        or not isinstance(judgment.get("supporting_provider_count"), int)
        or judgment["supporting_provider_count"] < 2
        or len(_sequence(judgment.get("citations"))) < 3
    ):
        raise P153StagingShadowError("incident judgment evidence threshold invalid")
    requests = _sequence(judgment.get("evidence_requests"))
    if len(requests) > _MAX_FOLLOW_UP_READS:
        raise P153StagingShadowError("judgment follow-up budget invalid")
    for request in requests:
        if (
            not isinstance(request, Mapping)
            or request.get("provider") not in _PROVIDERS
            or request.get("capability") != "read_only_follow_up"
            or not isinstance(request.get("reason"), str)
        ):
            raise P153StagingShadowError("judgment follow-up request invalid")


def _validate_summary(summary: Mapping[str, Any]) -> None:
    expected = {
        "source_count",
        "successful_source_count",
        "normalized_evidence_count",
        "new_evidence_count",
        "duplicate_evidence_count",
        "supporting_provider_count",
        "resume_count",
    }
    if set(summary) != expected:
        raise P153StagingShadowError("report summary invalid")
    for key, item in summary.items():
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise P153StagingShadowError(f"report summary counter invalid:{key}")


def _validate_audit(audit: Mapping[str, Any], *, require_real_network_zero: bool) -> None:
    expected = {
        "transport_call_count",
        "real_network_call_count",
        "retry_count",
        "follow_up_read_count",
        "redaction_count",
        "external_model_call_count",
        "write_request_count",
        "secret_persistence_count",
        "approval_count",
        "action_execution_count",
        "production_mutation_count",
    }
    if set(audit) != expected:
        raise P153StagingShadowError("report audit invalid")
    for key, item in audit.items():
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise P153StagingShadowError(f"report audit counter invalid:{key}")
    zero_keys = {
        "external_model_call_count",
        "write_request_count",
        "secret_persistence_count",
        "approval_count",
        "action_execution_count",
        "production_mutation_count",
    }
    if require_real_network_zero:
        zero_keys.add("real_network_call_count")
    for key in zero_keys:
        if audit[key] != 0:
            raise P153StagingShadowError(f"authority counter must be zero:{key}")


def _validate_self_hash(value: Mapping[str, Any], field: str) -> None:
    _require_hash(value.get(field), field)
    expected = stable_hash({key: item for key, item in value.items() if key != field})
    if value[field] != expected:
        raise P153StagingShadowError(f"{field} self hash invalid")


def _require_hash(value: Any, field: str) -> None:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise P153StagingShadowError(f"{field} invalid")


def _bounded_int(value: Any, minimum: int, maximum: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum or value > maximum:
        raise P153StagingShadowError(f"{field} invalid")
    return value


def _strict_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise P153StagingShadowError(f"{field} invalid")
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def _decode_json(body: bytes) -> Any:
    try:
        return json.loads(body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise P153StagingShadowError("provider returned invalid JSON") from exc


def _fingerprint(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()
