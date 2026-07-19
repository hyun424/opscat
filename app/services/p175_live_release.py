"""Canonical P175 predecessor closeout for P176.

This module does not re-run live operations. It fail-closed validates the
single qualified P175 live run produced by the P174 harness, binds the frozen
plan and reviewed harness identities, and emits reproducible closeout artifacts.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.p147_p152_contracts import file_hash, validate_self_hash, with_self_hash, write_canonical_json
from app.services.p174_live_harness import P174LiveHarnessError, verify_evidence_jsonl

QUALIFIED_RUN_ID = "p175-20260718T075733Z"
QUALIFIED_RUN_PATH = f"evals/p174/live/{QUALIFIED_RUN_ID}"
EXPECTED_P175_PLAN_HASH = "sha256:331b693b373b4a77e673c0be6d086fd8aec462625b461cda5c413fe450cb163e"
EXPECTED_HARNESS_MANIFEST_HASH = "sha256:1c06741375b109548714cce342672b111fc6be55dfdc35eb3ecdf7b709e1f280"
ORIGINAL_SUMMARY_FILE_HASH = "sha256:b84ba7feafe6df399603441f01919de16b328138f477213244b9e3b18972a7de"
ORIGINAL_JSONL_FILE_HASH = "sha256:05ce6e2f466ef578722d172ab8784a0af52269347e5dc77ba54f3b71a3ce8177"
ORIGINAL_JSONL_HASH = "sha256:c316df1189424e34f81eaaff020ce047fab00d2918b5022fabfa88ef775c3461"
ORIGINAL_TAIL_HASH = "sha256:edd5216b82fdebe08a76b23df7503de6d59b15ce003d0bc8d48482228adeb159"
EXPECTED_SUMMARY_FILE_HASH = "sha256:458e2c8a7ed6e5d11e8ab36eb48b663b1144f57cf6a8c7513e4a9911de9dfa07"
EXPECTED_JSONL_FILE_HASH = "sha256:183bc6f8199b1875d224ed572166abcbc226fce34289a62ac87641c74a19cc1d"
EXPECTED_JSONL_HASH = "sha256:7cb1aca9120a9bb9d9068e46e0880d5b1f4a12ab8b31707d4d5c66571532d406"
EXPECTED_TAIL_HASH = "sha256:2377fc43857e23caa7b17a5438ebaaf882d8c0aba125eca6619680804a62d6cd"
EXPECTED_MANIFEST_HASH = "sha256:0478e89ff32d75c7307e31f050d1b7a235e631148aed3a99cd543df652ccd293"

RELEASE_SCHEMA_VERSION = "p175.release_evidence.v1"
REVIEW_SCHEMA_VERSION = "p175.final_implementation_review.v1"
RELEASE_STATUS = "p175_live_qualification_closed_out"
RELEASE_CLAIM = "p175_disposable_live_lab_qualification_bound_for_p176_predecessor"
SOURCE_PATHS = (
    "app/services/p175_live_release.py",
    "scripts/finalize_p175_live_release.py",
    "tests/test_p175_live_release.py",
    "docs/tickets/p175/README.md",
)
LIMITATIONS = (
    "binds_existing_p175_live_harness_run_no_new_live_operation",
    "disposable_p174_gcp_lab_only_not_customer_production",
    "p176_requires_this_canonical_closeout_before_predecessor_acceptance",
)
PRODUCTION_BLOCKERS = (
    "no_customer_production_authority",
    "no_unbounded_provider_mutation_authority",
    "no_secret_or_credential_operation_claim",
)
DERIVATIVE_PROVENANCE = {
    "source": "p174_security_quarantine",
    "redaction_profile": "p175_predecessor_derivative_v1",
    "raw_payload_removed": True,
    "outcome_semantics_preserved": True,
    "original_summary_file_hash": ORIGINAL_SUMMARY_FILE_HASH,
    "original_jsonl_file_hash": ORIGINAL_JSONL_FILE_HASH,
    "original_jsonl_hash": ORIGINAL_JSONL_HASH,
    "original_tail_hash": ORIGINAL_TAIL_HASH,
}

_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_UUID7_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")


class P175LiveReleaseError(ValueError):
    """Raised when the P175 closeout cannot be proven safely."""


@dataclass(frozen=True)
class QualifiedRun:
    run_id: str
    run_path: str
    summary_path: str
    jsonl_path: str
    summary: Mapping[str, Any]
    summary_file_hash: str
    jsonl_file_hash: str
    verified_jsonl: Mapping[str, Any]


def load_qualified_run(project_root: Path) -> QualifiedRun:
    run_dir = project_root / QUALIFIED_RUN_ID
    if not run_dir.is_dir():
        run_dir = project_root / QUALIFIED_RUN_PATH
    if run_dir.name != QUALIFIED_RUN_ID or not run_dir.is_dir() or run_dir.is_symlink():
        raise P175LiveReleaseError("qualified_run_missing")
    summary_path = run_dir / "p175-live-summary.json"
    jsonl_path = run_dir / "p175-live-evidence.jsonl"
    summary = _read_json(summary_path, "summary")
    summary_file_hash = _file_hash(summary_path)
    jsonl_text = _read_text(jsonl_path, "evidence_jsonl")
    jsonl_file_hash = _file_hash(jsonl_path)
    try:
        verified_jsonl = verify_evidence_jsonl(jsonl_text)
    except (P174LiveHarnessError, json.JSONDecodeError, KeyError) as exc:
        raise P175LiveReleaseError("evidence_chain_invalid") from exc
    _validate_summary(summary, verified_jsonl, summary_file_hash, jsonl_file_hash)
    return QualifiedRun(
        run_id=QUALIFIED_RUN_ID,
        run_path=QUALIFIED_RUN_PATH,
        summary_path=f"{QUALIFIED_RUN_PATH}/p175-live-summary.json",
        jsonl_path=f"{QUALIFIED_RUN_PATH}/p175-live-evidence.jsonl",
        summary=summary,
        summary_file_hash=summary_file_hash,
        jsonl_file_hash=jsonl_file_hash,
        verified_jsonl=verified_jsonl,
    )


def assemble_release_evidence(run: QualifiedRun, review: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    _validate_review(review, run)
    summary = dict(run.summary)
    closeout = _canonical_closeout(run)
    release = {
        "schema_version": RELEASE_SCHEMA_VERSION,
        "phase": "p175",
        "status": RELEASE_STATUS,
        "claim": RELEASE_CLAIM,
        "limitations": list(LIMITATIONS),
        "plan_hash": EXPECTED_P175_PLAN_HASH,
        "harness_manifest_hash": EXPECTED_HARNESS_MANIFEST_HASH,
        "predecessor_closeout": closeout,
        "review": dict(review),
        "source_hashes": _source_hashes(project_root),
        "metrics": _canonical_metrics(summary, run),
        "production_blockers": list(PRODUCTION_BLOCKERS),
        "counters": _canonical_counters(),
    }
    return with_self_hash(release, "evidence_hash")


def _canonical_closeout(run: QualifiedRun) -> dict[str, Any]:
    summary = dict(run.summary)
    return {
        "qualified_run_id": run.run_id,
        "run_path": run.run_path,
        "summary": {
            "path": run.summary_path,
            "file_hash": run.summary_file_hash,
            "schema_version": summary["schema_version"],
            "status": summary["status"],
            "qualified": summary["qualified"],
            "manifest_hash": summary["manifest_hash"],
            "gates": summary["gates"],
            "campaign": summary["campaign"],
            "coverage_counters": summary["coverage_counters"],
            "failure_count": summary["failure_count"],
        },
        "evidence_jsonl": {
            "path": run.jsonl_path,
            "file_hash": run.jsonl_file_hash,
            **dict(run.verified_jsonl),
        },
        "derivative_provenance": DERIVATIVE_PROVENANCE,
    }


def _canonical_metrics(summary: Mapping[str, Any], run: QualifiedRun) -> dict[str, Any]:
    return {
        "healthy_windows": summary["gates"]["healthy_window"]["observed_consecutive"],
        "scenario_episodes": summary["gates"]["scenario_campaign"]["observed_successful"],
        "evidence_event_count": run.verified_jsonl["event_count"],
        "production_ready": False,
    }


def _canonical_counters() -> dict[str, int]:
    return {
        "credential_read_count": 0,
        "external_model_call_count": 0,
        "external_network_call_count": 0,
        "production_mutation_count": 0,
        "shell_execution_count": 0,
        "staging_mutation_count": 0,
    }


def build_release_evidence(review: Mapping[str, Any], project_root: Path = Path.cwd()) -> dict[str, Any]:
    run = load_qualified_run(project_root)
    return assemble_release_evidence(run, review, project_root=project_root)


def validate_release_evidence(evidence: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    if evidence.get("schema_version") != RELEASE_SCHEMA_VERSION:
        raise P175LiveReleaseError("release_schema_invalid")
    if evidence.get("phase") != "p175" or evidence.get("status") != RELEASE_STATUS:
        raise P175LiveReleaseError("release_status_invalid")
    review = evidence.get("review")
    if not isinstance(review, Mapping):
        raise P175LiveReleaseError("review_missing")
    validate_self_hash(evidence, "evidence_hash")
    run = load_qualified_run(project_root)
    _validate_review(review, run)
    if evidence.get("plan_hash") != EXPECTED_P175_PLAN_HASH:
        raise P175LiveReleaseError("plan_hash_mismatch")
    if evidence.get("harness_manifest_hash") != EXPECTED_HARNESS_MANIFEST_HASH:
        raise P175LiveReleaseError("harness_manifest_hash_mismatch")
    if (
        evidence.get("claim") != RELEASE_CLAIM
        or evidence.get("limitations") != list(LIMITATIONS)
        or evidence.get("production_blockers") != list(PRODUCTION_BLOCKERS)
        or evidence.get("metrics") != _canonical_metrics(run.summary, run)
        or evidence.get("counters") != _canonical_counters()
        or evidence.get("predecessor_closeout") != _canonical_closeout(run)
    ):
        raise P175LiveReleaseError("release_derived_facts_mismatch")
    if evidence.get("source_hashes") != _source_hashes(project_root):
        raise P175LiveReleaseError("source_hashes_mismatch")
    closeout = _mapping(evidence.get("predecessor_closeout"), "predecessor_closeout")
    if closeout.get("qualified_run_id") != QUALIFIED_RUN_ID:
        raise P175LiveReleaseError("qualified_run_mismatch")
    summary = _mapping(closeout.get("summary"), "summary")
    jsonl = _mapping(closeout.get("evidence_jsonl"), "evidence_jsonl")
    if summary.get("file_hash") != run.summary_file_hash or jsonl.get("file_hash") != run.jsonl_file_hash:
        raise P175LiveReleaseError("predecessor_file_hash_mismatch")
    if jsonl.get("tail_hash") != run.verified_jsonl["tail_hash"] or jsonl.get("jsonl_hash") != run.verified_jsonl["jsonl_hash"]:
        raise P175LiveReleaseError("predecessor_chain_mismatch")
    if any(value != 0 for value in _mapping(evidence.get("counters"), "counters").values()):
        raise P175LiveReleaseError("forbidden_counter_nonzero")
    return {"status": evidence["status"], "evidence_hash": evidence["evidence_hash"], "review_hash": review["review_hash"]}


def write_release_artifacts(review_path: Path, project_root: Path = Path.cwd()) -> dict[str, Path]:
    run = load_qualified_run(project_root)
    review = _read_json(review_path, "external_review")
    release = assemble_release_evidence(run, review, project_root=project_root)
    validate_release_evidence(release, project_root=project_root)
    release_path = project_root / "evals/p175/output/release-evidence.json"
    write_canonical_json(release_path, release)
    return {"release": release_path}


def _validate_summary(summary: Mapping[str, Any], verified_jsonl: Mapping[str, Any], summary_file_hash: str, jsonl_file_hash: str) -> None:
    if summary.get("schema_version") != "p174.live_harness_summary.v1":
        raise P175LiveReleaseError("summary_schema_invalid")
    if summary.get("status") != "qualified" or summary.get("qualified") is not True or summary.get("fail_closed") is not False:
        raise P175LiveReleaseError("summary_not_qualified")
    if summary.get("diagnostic_campaign_only") is not False or summary.get("failure_count") != 0 or summary.get("failures") != []:
        raise P175LiveReleaseError("summary_not_qualified")
    if summary.get("manifest_hash") != EXPECTED_MANIFEST_HASH:
        raise P175LiveReleaseError("summary_manifest_mismatch")
    if summary.get("derivative_provenance") != DERIVATIVE_PROVENANCE:
        raise P175LiveReleaseError("summary_derivative_provenance_mismatch")
    gates = _mapping(summary.get("gates"), "gates")
    healthy = _mapping(gates.get("healthy_window"), "healthy_window")
    scenarios = _mapping(gates.get("scenario_campaign"), "scenario_campaign")
    if healthy.get("required_consecutive") != 200 or healthy.get("observed_consecutive") != 200 or healthy.get("passed") is not True:
        raise P175LiveReleaseError("summary_healthy_gate_invalid")
    if scenarios.get("required_exact") != 100 or scenarios.get("observed_successful") != 100 or scenarios.get("passed") is not True:
        raise P175LiveReleaseError("summary_scenario_gate_invalid")
    evidence = _mapping(summary.get("evidence"), "evidence")
    if evidence.get("event_count") != 301 or evidence.get("tail_hash") != EXPECTED_TAIL_HASH or evidence.get("jsonl_hash") != EXPECTED_JSONL_HASH:
        raise P175LiveReleaseError("summary_chain_mismatch")
    if dict(verified_jsonl) != {
        "schema_version": "p174.live_harness_evidence.v1",
        "event_count": 301,
        "tail_hash": EXPECTED_TAIL_HASH,
        "jsonl_hash": EXPECTED_JSONL_HASH,
    }:
        raise P175LiveReleaseError("summary_chain_mismatch")
    if summary_file_hash != EXPECTED_SUMMARY_FILE_HASH or jsonl_file_hash != EXPECTED_JSONL_FILE_HASH:
        raise P175LiveReleaseError("qualified_run_file_hash_mismatch")


def _validate_review(review: Mapping[str, Any], run: QualifiedRun) -> None:
    if set(review) != {
        "schema_version",
        "phase",
        "decision",
        "writer_id",
        "reviewer_id",
        "reviewer_identity",
        "review_source",
        "reviewed_at",
        "findings",
        "limitations",
        "reviewed_run",
        "reviewed_plan_hash",
        "reviewed_harness_manifest_hash",
        "review_hash",
    }:
        raise P175LiveReleaseError("review_schema_invalid")
    if review.get("schema_version") != REVIEW_SCHEMA_VERSION or review.get("phase") != "p175":
        raise P175LiveReleaseError("review_schema_invalid")
    if review.get("decision") != "approve":
        raise P175LiveReleaseError("review_missing")
    if (
        _UUID7_RE.fullmatch(str(review.get("writer_id", ""))) is None
        or _UUID7_RE.fullmatch(str(review.get("reviewer_id", ""))) is None
        or review.get("writer_id") == review.get("reviewer_id")
    ):
        raise P175LiveReleaseError("reviewer_independence_required")
    if (
        review.get("review_source") != "codex_native_subagent"
        or not review.get("reviewer_identity")
        or not isinstance(review.get("findings"), Mapping)
        or not _UTC_RE.fullmatch(str(review.get("reviewed_at", "")))
        or review.get("limitations") != list(LIMITATIONS)
    ):
        raise P175LiveReleaseError("review_metadata_invalid")
    if dict(review["findings"]) != {"p0": 0, "p1": 0, "p2": 0, "p3": 0}:
        raise P175LiveReleaseError("review_findings_not_clean")
    validate_self_hash(review, "review_hash")
    reviewed_run = _mapping(review.get("reviewed_run"), "reviewed_run")
    if reviewed_run.get("qualified_run_id") != run.run_id:
        raise P175LiveReleaseError("review_run_mismatch")
    if reviewed_run.get("summary_file_hash") != run.summary_file_hash or reviewed_run.get("jsonl_file_hash") != run.jsonl_file_hash:
        raise P175LiveReleaseError("review_file_hash_mismatch")
    if reviewed_run.get("jsonl_hash") != run.verified_jsonl["jsonl_hash"] or reviewed_run.get("tail_hash") != run.verified_jsonl["tail_hash"]:
        raise P175LiveReleaseError("review_chain_mismatch")
    if review.get("reviewed_plan_hash") != EXPECTED_P175_PLAN_HASH:
        raise P175LiveReleaseError("review_plan_hash_mismatch")
    if review.get("reviewed_harness_manifest_hash") != EXPECTED_HARNESS_MANIFEST_HASH:
        raise P175LiveReleaseError("review_harness_manifest_hash_mismatch")


def _source_hashes(project_root: Path) -> dict[str, str]:
    return {path: file_hash(project_root / path) for path in SOURCE_PATHS}


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(_read_text(path, label), object_pairs_hook=_strict_object)
    except json.JSONDecodeError as exc:
        raise P175LiveReleaseError(f"{label}_json_invalid") from exc
    if not isinstance(value, dict):
        raise P175LiveReleaseError(f"{label}_object_required")
    return value


def _read_text(path: Path, label: str) -> str:
    if not path.is_file() or path.is_symlink():
        raise P175LiveReleaseError(f"{label}_missing")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise P175LiveReleaseError(f"{label}_read_failed") from exc


def _file_hash(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise P175LiveReleaseError(f"file_missing:{path}")
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate_key:{key}")
        result[key] = value
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P175LiveReleaseError(f"{label}_object_required")
    return value


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and _HASH_RE.fullmatch(value) is not None


def clone_without_hash(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a mutable copy without changing canonical order semantics."""

    cloned = deepcopy(dict(value))
    if not _is_hash(cloned.get("evidence_hash")):
        raise P175LiveReleaseError("evidence_hash_invalid")
    return cloned
