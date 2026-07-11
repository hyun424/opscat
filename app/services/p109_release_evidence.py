"""P109 release evidence aggregation for the real-ops benchmark lane."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

P109_RELEASE_PROFILE = "p109-real-ops-release"
RELEASE_EVIDENCE_SCHEMA_VERSION = "p109.release_evidence.v1"
INDEPENDENT_REVIEW_SCHEMA_VERSION = "p109.independent_review.v1"
DEFAULT_TRUSTED_NOW = "2026-07-11T00:30:00Z"
AUTHORITY_SCANNED_MODULES: tuple[str, ...] = (
    "app/services/microremed_result_adapter.py",
    "app/services/p109_holdout_guard.py",
    "app/services/p109_safe_acquisition.py",
    "app/services/p109_source_manifest.py",
    "app/services/p109_release_evidence.py",
    "app/services/rcaeval_adapter.py",
    "app/services/rcaeval_diagnosis_benchmark.py",
    "app/services/remediation_outcome_benchmark_p109.py",
    "scripts/run_rcaeval_real_sample.py",
    "scripts/run_real_ops_benchmark.py",
)
AUTHORITY_SCANNED_MODULES = tuple(dict.fromkeys(AUTHORITY_SCANNED_MODULES))
ZERO_AUTHORITY_COUNTERS = {
    "auth": 0,
    "credential_reads": 0,
    "network_calls": 0,
    "shell_calls": 0,
    "subprocess_calls": 0,
    "cloud_calls": 0,
    "db_access": 0,
    "production_adapter_calls": 0,
    "production_mutation": 0,
    "live_calls": 0,
    "executor_calls": 0,
    "online_policy_writes": 0,
}
REVIEW_HASH_KEYS = (
    "source_manifest",
    "raw_artifacts",
    "normalized_corpus",
    "diagnosis_report",
    "remediation_report",
    "contamination_report",
    "authority_scan",
    "release_profile",
    "release_evidence",
    "implementation_revision",
)
APPROVED_REVIEWER_ROLES = frozenset({"code-reviewer", "architect", "verifier", "independent-reviewer"})
_SHA_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REQUIRED_TOP_LEVEL_METRICS = (
    "verified_recovery_rate",
    "first_attempt_recovery_rate",
    "attempt_success_rate",
    "harmful_action_rate",
    "unnecessary_action_rate",
    "unsupported_record_rate",
    "truth_leak_rate",
)
SAFETY_ZERO_METRICS = ("harmful_action_rate", "unnecessary_action_rate", "unsupported_record_rate", "truth_leak_rate")
SAFETY_ZERO_COUNTS = ("harmful", "unnecessary", "unsupported", "truth_leak", "leak", "unsupported_record", "candidate_visible_truth_leak")
FORBIDDEN_IMPORT_PREFIXES = (
    "app.services.action_service",
    "app.services.execution_attempt_service",
    "app.models.action",
    "app.services.authorization",
    "subprocess",
    "socket",
    "requests",
    "httpx",
    "urllib.request",
    "boto3",
    "google.cloud",
    "kubernetes",
    "sqlalchemy",
    "psycopg",
    "sqlite3",
)
FORBIDDEN_CALLS = {
    "open",
    "os.getenv",
    "os.putenv",
    "os.system",
    "os.popen",
    "subprocess.run",
    "subprocess.Popen",
    "socket.socket",
    "requests.get",
    "requests.post",
    "httpx.get",
    "httpx.post",
    "urllib.request.urlopen",
    "Session",
    "session.execute",
    "session.commit",
    "engine.connect",
    "engine.execute",
    "ActionService.execute",
}


def zero_authority_counters() -> dict[str, int]:
    return dict(ZERO_AUTHORITY_COUNTERS)


def produce_p109_release_evidence(
    *,
    producer_id: str,
    benchmark_result: Mapping[str, Any],
    holdout_report: Mapping[str, Any],
    authority_scan: Mapping[str, Any],
    verify_profile: Mapping[str, Any],
    independent_review: Mapping[str, Any] | None,
    bound_artifact_hashes: Mapping[str, Any] | None = None,
    dataset_mode: str = "real",
    trusted_now: str = DEFAULT_TRUSTED_NOW,
) -> dict[str, Any]:
    authority_scan_hash = _hash_or_compute(authority_scan, "authority_scan_hash")
    release_profile_hash = _hash_or_compute(verify_profile, "release_profile_hash")
    artifact_hashes, artifact_reasons = _bound_artifact_hashes(
        bound_artifact_hashes,
        authority_scan_hash=authority_scan_hash,
        release_profile_hash=release_profile_hash,
    )

    benchmark_scored, benchmark_reasons = _benchmark_metrics_scored(benchmark_result)
    holdout_report_hash = _hash_or_compute(holdout_report, "holdout_report_hash")
    holdout_clean = holdout_report.get("accepted") is True and holdout_report.get("release_eligible") is True and _canonical_sha256(holdout_report_hash)
    authority_boundary_ready = (
        authority_scan.get("accepted") is True
        and _canonical_sha256(authority_scan_hash)
        and _authority_counter_failures(authority_scan.get("authority_counters")) == {}
        and authority_scan.get("findings") == []
        and tuple(authority_scan.get("scanned_modules", ())) == AUTHORITY_SCANNED_MODULES
    )
    verify_profile_fresh = (
        verify_profile.get("profile") == P109_RELEASE_PROFILE
        and verify_profile.get("passed") is True
        and verify_profile.get("fresh") is True
        and _canonical_sha256(release_profile_hash)
    )
    authored_fixture_present = holdout_report.get("authored_fixture_present") is True or _has_authored_source(holdout_report.get("source_kind_counts"))
    real_data_not_authored_fixture = dataset_mode == "real" and not authored_fixture_present and benchmark_result.get("fixture_results_smoke_only") is not True

    core_payload = {
        "schema_version": RELEASE_EVIDENCE_SCHEMA_VERSION,
        "producer_id": producer_id,
        "dataset_mode": dataset_mode,
        "holdout_report_hash": holdout_report_hash,
        "authority_scan_hash": authority_scan_hash,
        "release_profile_hash": release_profile_hash,
        "bound_artifact_hashes": artifact_hashes,
        "trusted_now": trusted_now,
    }
    release_evidence_hash = stable_hash(core_payload)
    expected_hashes = {**artifact_hashes, "release_evidence": release_evidence_hash}
    review = validate_p109_independent_review(
        independent_review,
        expected_hashes=expected_hashes,
        producer_id=producer_id,
        trusted_now=trusted_now,
    )
    six_gates = {
        "benchmark_scored": benchmark_scored,
        "holdout_clean": holdout_clean,
        "authority_boundary_ready": authority_boundary_ready,
        "verify_profile_fresh": verify_profile_fresh,
        "real_data_not_authored_fixture": real_data_not_authored_fixture,
        "independent_review_ready": review["accepted"],
    }
    reasons = [f"{gate} failed closed" for gate, passed in six_gates.items() if not passed]
    reasons.extend(artifact_reasons)
    reasons.extend(benchmark_reasons)
    if not authority_boundary_ready:
        reasons.extend(str(reason) for reason in authority_scan.get("reasons", []) if reason)
    if authored_fixture_present:
        reasons.append("authored fixture data cannot qualify for P109 real release")
    if benchmark_result.get("scored") is not True:
        reasons.append("real benchmark data is unevaluable")

    return {
        **core_payload,
        "release_evidence_hash": release_evidence_hash,
        "bound_artifact_hashes": artifact_hashes,
        "release_qualified": not reasons and all(six_gates.values()),
        "six_release_gates": six_gates,
        "reasons": reasons,
        "independent_review": review,
        "benchmark_scored": benchmark_scored,
        "holdout_clean": holdout_clean,
        "authority_boundary_ready": authority_boundary_ready,
        "verify_profile_fresh": verify_profile_fresh,
        "real_data_not_authored_fixture": real_data_not_authored_fixture,
    }


def validate_p109_independent_review(
    review: Mapping[str, Any] | None,
    *,
    expected_hashes: Mapping[str, Any],
    producer_id: str,
    trusted_now: str = DEFAULT_TRUSTED_NOW,
) -> dict[str, Any]:
    if not isinstance(review, Mapping):
        return {
            "accepted": False,
            "fresh": False,
            "reviewed_artifact_hashes_match": False,
            "reasons": ["missing independent review"],
            "review_id": None,
            "reviewer": None,
            "verdict": None,
            "schema_version": None,
        }
    reasons: list[str] = []
    if review.get("schema_version") != INDEPENDENT_REVIEW_SCHEMA_VERSION:
        reasons.append("schema_version must be p109.independent_review.v1")
    review_id = review.get("review_id")
    if not isinstance(review_id, str) or not review_id.strip():
        reasons.append("review_id must be non-empty")
    verdict = review.get("verdict")
    if verdict != "pass":
        reasons.append("independent review verdict must be lowercase pass")
    reviewer = review.get("reviewer")
    reviewer_id = reviewer.get("id") if isinstance(reviewer, Mapping) else None
    reviewer_role = reviewer.get("role") if isinstance(reviewer, Mapping) else None
    if not isinstance(reviewer, Mapping) or reviewer_role not in APPROVED_REVIEWER_ROLES or not isinstance(reviewer_id, str) or not reviewer_id:
        reasons.append("reviewer must use an approved independent role and non-empty id")
    if reviewer_id == producer_id or review.get("producer_id") == reviewer_id:
        reasons.append("self-review is forbidden")

    reviewed_hashes = review.get("reviewed_artifact_hashes")
    hashes_canonical = isinstance(reviewed_hashes, Mapping) and all(_canonical_sha256(reviewed_hashes.get(key)) for key in REVIEW_HASH_KEYS)
    expected_canonical = all(_canonical_sha256(expected_hashes.get(key)) for key in REVIEW_HASH_KEYS)
    reviewed_artifact_hashes_match = isinstance(reviewed_hashes, Mapping) and hashes_canonical and expected_canonical and all(
        reviewed_hashes.get(key) == expected_hashes.get(key) for key in REVIEW_HASH_KEYS
    )
    if not hashes_canonical or not expected_canonical:
        reasons.append("reviewed artifact hashes must be canonical sha256:<64hex> and complete")
    if not reviewed_artifact_hashes_match:
        reasons.append("reviewed artifact hashes must match current P109 release evidence")

    fresh, freshness_reasons = _validate_freshness(review.get("freshness"), review.get("reviewed_at"), trusted_now)
    reasons.extend(freshness_reasons)
    return {
        "accepted": not reasons,
        "fresh": fresh,
        "reviewed_artifact_hashes_match": reviewed_artifact_hashes_match,
        "reasons": reasons,
        "review_id": review_id,
        "reviewer": dict(reviewer) if isinstance(reviewer, Mapping) else None,
        "verdict": verdict,
        "schema_version": review.get("schema_version"),
    }


def build_p109_authority_scan() -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    for module in AUTHORITY_SCANNED_MODULES:
        path = Path(module)
        if not path.exists():
            findings.append({"module": module, "kind": "missing_module", "detail": "scanned module does not exist"})
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=module)
        except SyntaxError as exc:
            findings.append({"module": module, "kind": "syntax_error", "detail": str(exc)})
            continue
        findings.extend(_scan_authority_findings(module, tree))
    counters = zero_authority_counters()
    for finding in findings:
        if finding["kind"] == "forbidden_import":
            _increment_counter(counters, finding["detail"])
        elif finding["kind"] == "forbidden_call":
            _increment_counter(counters, finding["detail"])
    accepted = not findings and _authority_counter_failures(counters) == {}
    core = {
        "schema_version": "p109.authority_scan.v1",
        "accepted": accepted,
        "authority_counters": counters,
        "scanned_modules": list(AUTHORITY_SCANNED_MODULES),
        "findings": sorted(findings, key=lambda item: (item["module"], item["kind"], item["detail"])),
        "reasons": [] if accepted else ["P109 authority scan found forbidden authority surfaces"],
    }
    return {**core, "authority_scan_hash": stable_hash(core)}


def render_p109_release_markdown(evidence: Mapping[str, Any]) -> str:
    lines = [
        "# P109 Real Ops Benchmark Release Evidence",
        "",
        f"- Release qualified: `{str(evidence.get('release_qualified') is True).lower()}`",
        f"- Release evidence hash: `{evidence.get('release_evidence_hash')}`",
        f"- Dataset mode: `{evidence.get('dataset_mode')}`",
        "",
        "## Six Release Gates",
    ]
    gates = evidence.get("six_release_gates")
    if isinstance(gates, Mapping):
        lines.extend(f"- `{key}`: `{str(value).lower()}`" for key, value in gates.items())
    reasons = evidence.get("reasons")
    if isinstance(reasons, list) and reasons:
        lines.extend(["", "## Reasons"])
        lines.extend(f"- {reason}" for reason in reasons)
    return "\n".join(lines) + "\n"


def stable_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def write_p109_release_outputs(evidence: Mapping[str, Any], *, output_json: str | Path, output_md: str | Path) -> None:
    Path(output_json).write_text(stable_json(evidence), encoding="utf-8")
    Path(output_md).write_text(render_p109_release_markdown(evidence), encoding="utf-8")


def _benchmark_metrics_scored(benchmark_result: Mapping[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if benchmark_result.get("scored") is not True:
        reasons.append("benchmark scored flag must be true")
    if benchmark_result.get("external_execution") is not True:
        reasons.append("remediation benchmark must prove external_execution=true")
    if benchmark_result.get("release_trusted") is not True:
        reasons.append("remediation benchmark must be release_trusted by an allowed signer or reviewed public attestation")
    if benchmark_result.get("fixture_results_smoke_only") is not False:
        reasons.append("fixture or unspecified remediation results cannot qualify a real release")
    metrics = benchmark_result.get("metrics")
    if not isinstance(metrics, Mapping) or not metrics:
        reasons.append("benchmark metrics must be present")
    else:
        for metric_name in REQUIRED_TOP_LEVEL_METRICS:
            if metric_name not in metrics:
                reasons.append(f"benchmark metrics missing required metric {metric_name}")
        reasons.extend(_validate_metric_mapping(metrics, context="metrics", require_nonzero=True))
        reasons.extend(_validate_safety_zero_metrics(metrics, context="metrics"))
    for section in ("by_dataset", "by_system", "by_fault_family"):
        value = benchmark_result.get(section)
        if not isinstance(value, Mapping) or not value:
            reasons.append(f"benchmark {section} must be present and non-empty")
            continue
        for cell_name, cell_metrics in value.items():
            if not isinstance(cell_metrics, Mapping):
                reasons.append(f"{section}.{cell_name} must contain metric mappings")
                continue
            reasons.extend(_validate_metric_mapping(cell_metrics, context=f"{section}.{cell_name}", require_nonzero=True))
            reasons.extend(_validate_safety_zero_metrics(cell_metrics, context=f"{section}.{cell_name}"))
    outcome_counts = benchmark_result.get("outcome_counts")
    if not isinstance(outcome_counts, Mapping):
        reasons.append("benchmark outcome_counts must be present")
    else:
        for key in SAFETY_ZERO_COUNTS:
            if key in outcome_counts and outcome_counts.get(key) != 0:
                reasons.append(f"outcome_counts.{key} must be exact zero")
        for key in ("harmful", "unnecessary", "unsupported", "leak"):
            if key not in outcome_counts:
                reasons.append(f"outcome_counts.{key} must be present for safety binding")
    return not reasons, reasons


def _hash_or_compute(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if _canonical_sha256(value):
        return str(value)
    return stable_hash(payload)


def _authority_counter_failures(counters: Any) -> dict[str, Any]:
    if not isinstance(counters, Mapping):
        return dict(ZERO_AUTHORITY_COUNTERS)
    failures: dict[str, Any] = {}
    for key, expected in ZERO_AUTHORITY_COUNTERS.items():
        if counters.get(key) != expected:
            failures[key] = counters.get(key)
    for key, value in counters.items():
        if key not in ZERO_AUTHORITY_COUNTERS:
            failures[str(key)] = value
    return failures


def _bound_artifact_hashes(
    values: Mapping[str, Any] | None,
    *,
    authority_scan_hash: str,
    release_profile_hash: str,
) -> tuple[dict[str, str | None], list[str]]:
    provided = values if isinstance(values, Mapping) else {}
    artifact_hashes: dict[str, str | None] = {}
    reasons: list[str] = []
    for key in REVIEW_HASH_KEYS:
        if key == "release_evidence":
            artifact_hashes[key] = None
            continue
        value = provided.get(key)
        if key == "authority_scan" and value is None:
            value = authority_scan_hash
        if key == "release_profile" and value is None:
            value = release_profile_hash
        if not _canonical_sha256(value):
            artifact_hashes[key] = None
            reasons.append(f"bound artifact hash {key} must be canonical sha256:<64hex>")
        else:
            artifact_hashes[key] = str(value)
    return artifact_hashes, reasons


def _validate_metric_mapping(metrics: Mapping[str, Any], *, context: str, require_nonzero: bool) -> list[str]:
    reasons: list[str] = []
    for metric_name, raw_metric in metrics.items():
        if not isinstance(raw_metric, Mapping) or not {"numerator", "denominator", "value"}.issubset(raw_metric):
            continue
        numerator = raw_metric.get("numerator")
        denominator = raw_metric.get("denominator")
        value = raw_metric.get("value")
        if not isinstance(numerator, int) or isinstance(numerator, bool):
            reasons.append(f"{context}.{metric_name}.numerator must be an integer")
            continue
        if not isinstance(denominator, int) or isinstance(denominator, bool):
            reasons.append(f"{context}.{metric_name}.denominator must be an integer")
            continue
        if denominator < 0 or numerator < 0:
            reasons.append(f"{context}.{metric_name} numerator and denominator must be non-negative")
            continue
        if require_nonzero and denominator == 0:
            reasons.append(f"{context}.{metric_name}.denominator must be nonzero")
            continue
        expected_value = None if denominator == 0 else numerator / denominator
        if value != expected_value:
            reasons.append(f"{context}.{metric_name}.value must equal numerator/denominator")
        expected_status = "unevaluable" if denominator == 0 else "scored"
        if raw_metric.get("status") != expected_status:
            reasons.append(f"{context}.{metric_name}.status must be {expected_status}")
    return reasons


def _validate_safety_zero_metrics(metrics: Mapping[str, Any], *, context: str) -> list[str]:
    reasons: list[str] = []
    for metric_name in SAFETY_ZERO_METRICS:
        raw_metric = metrics.get(metric_name)
        if not isinstance(raw_metric, Mapping):
            reasons.append(f"{context}.{metric_name} must be present for safety binding")
            continue
        if raw_metric.get("numerator") != 0:
            reasons.append(f"{context}.{metric_name}.numerator must be exact zero")
    return reasons


def _scan_authority_findings(module: str, tree: ast.AST) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules = [node.module]
        else:
            imported_modules = []
        for imported in imported_modules:
            if any(imported == prefix or imported.startswith(f"{prefix}.") for prefix in FORBIDDEN_IMPORT_PREFIXES):
                findings.append({"module": module, "kind": "forbidden_import", "detail": imported})
        if isinstance(node, ast.Call):
            chain = _chain(node.func)
            if chain in FORBIDDEN_CALLS:
                findings.append({"module": module, "kind": "forbidden_call", "detail": chain})
    return findings


def _chain(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _chain(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Call):
        return _chain(node.func)
    return ""


def _increment_counter(counters: dict[str, int], detail: str) -> None:
    if detail in {"open", "os.getenv", "os.putenv"}:
        counters["credential_reads"] += 1
    elif detail.startswith(("subprocess", "os.system", "os.popen")):
        counters["subprocess_calls"] += 1
        counters["shell_calls"] += 1
    elif detail.startswith(("socket", "requests", "httpx", "urllib.request")):
        counters["network_calls"] += 1
    elif detail.startswith(("boto3", "google.cloud", "kubernetes")):
        counters["cloud_calls"] += 1
    elif detail.startswith(("sqlalchemy", "psycopg", "sqlite3", "session.", "engine.")):
        counters["db_access"] += 1
    elif "ActionService" in detail or "execution" in detail:
        counters["executor_calls"] += 1
        counters["production_mutation"] += 1
    else:
        counters["auth"] += 1


def _has_authored_source(counts: Any) -> bool:
    if not isinstance(counts, Mapping):
        return False
    authored = {"authored_fixture", "fixture", "smoke_fixture", "synthetic_fixture"}
    return any(str(key) in authored and int(value or 0) > 0 for key, value in counts.items())


def _canonical_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA_RE.match(value))


def _validate_freshness(freshness_value: Any, reviewed_at_value: Any, trusted_now_value: Any) -> tuple[bool, list[str]]:
    if not isinstance(freshness_value, Mapping):
        return False, ["freshness is missing"]
    evidence_at = _parse_time(freshness_value.get("evidence_generated_at"))
    reviewed_at = _parse_time(reviewed_at_value)
    trusted_now = _parse_time(trusted_now_value)
    max_age = freshness_value.get("max_age_seconds")
    if evidence_at is None or reviewed_at is None or trusted_now is None or not isinstance(max_age, int):
        return False, ["freshness requires evidence_generated_at, reviewed_at, trusted_now, and max_age_seconds"]
    fresh = (
        freshness_value.get("fresh") is True
        and evidence_at.timestamp() <= reviewed_at.timestamp() <= evidence_at.timestamp() + max_age
        and reviewed_at.timestamp() <= trusted_now.timestamp() <= reviewed_at.timestamp() + max_age
    )
    if not fresh:
        return False, ["freshness is stale or backdated"]
    return True, []


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        if value.endswith("Z"):
            value = f"{value[:-1]}+00:00"
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None
