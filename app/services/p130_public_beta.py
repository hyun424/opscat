"""P130 public-beta evidence aggregation with fail-closed promotion gates."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import P121_AUTHORITY_COUNTER_KEYS, zero_authority_counters

P130_PHASES = tuple(range(123, 130))
P130_CLAIM_LEDGER_SCHEMA_VERSION = "p130.claim_ledger.v1"
P130_RISK_REGISTER_SCHEMA_VERSION = "p130.risk_register.v1"
P130_BETA_EVIDENCE_SCHEMA_VERSION = "p130.beta_evidence.v1"
P130_RELEASE_EVIDENCE_SCHEMA_VERSION = "p130.release_evidence.v1"
P130_READY_STATUS = "p130_public_beta_qualified"
P130_BLOCKED_STATUS = "p130_blocked"

_ROOT = Path(__file__).resolve().parents[2]
_CLAIM_STATUSES = frozenset({"supported", "limited", "blocked"})
_RISK_SEVERITIES = frozenset({"low", "medium", "high", "critical"})
_BLOCKING_SEVERITIES = frozenset({"high", "critical"})
_CLOSED_RISK_STATUSES = frozenset({"closed", "mitigated", "accepted"})
_FORBIDDEN_CLAIM_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bproduction[- ]ready\b",
        r"\bproduction autonomy\b",
        r"\bproduction remediation\b",
        r"\blive[- ]production\b",
        r"\breal staging\b",
        r"\bstaging mutation\b",
        r"\bproduction mutation\b",
        r"\blive connector proof\b",
        r"\bauth completion\b",
        r"\bauth complete\b",
        r"\boperator replacement\b",
        r"\brequires credentials\b",
        r"\bcredential requirement\b",
        r"\bcredentialed execution\b",
    )
)


def build_p130_public_beta(*, root: Path = _ROOT, builder_id: str = "autonomous-builder", reviewer_id: str = "independent-p130-verifier") -> dict[str, dict[str, Any]]:
    """Aggregate P123-P129 evidence and P130 beta inputs into hash-bound outputs.

    The returned bundle always includes all four P130 artifacts. The status is
    promoted only when every gate is true; missing inputs produce blocked
    artifacts with explicit reasons.
    """

    upstream = {f"p{phase}": _read_json(root / f"evals/p{phase}/release-evidence.json") for phase in P130_PHASES}
    review = _read_json(root / "evals/p130/independent-review.json")
    claim_inputs = _load_input_records(root, schema="p130.claim_input.v1", key="claims")
    risk_inputs = _load_input_records(root, schema="p130.risk_input.v1", key="risks")
    feedback = _first_input(root, schema="p130.feedback_input.v1")
    exit_policy = _first_input(root, schema="p130.exit_policy_input.v1")

    upstream_hashes = {phase: _release_hash(evidence) for phase, evidence in upstream.items()}
    upstream_hashes_current = {
        phase: _hash_current(evidence, "release_evidence_hash")
        for phase, evidence in upstream.items()
    }
    upstream_status_ready = {
        phase: _upstream_ready(evidence)
        for phase, evidence in upstream.items()
    }
    authority_zero_by_phase = {
        phase: _evidence_authority_zero(evidence)
        for phase, evidence in upstream.items()
    }

    claim_ledger = _build_claim_ledger(claim_inputs, upstream_hashes=upstream_hashes)
    risk_register = _build_risk_register(risk_inputs)
    input_hashes = _input_hashes(root)

    review_current = _review_current(
        review,
        reviewer_id=reviewer_id,
        builder_id=builder_id,
        upstream_hashes=upstream_hashes,
    )
    feedback_safe = _feedback_safe(feedback)
    visible_withdrawal = (
        claim_ledger["missing_withdrawal_path_count"] == 0
        and bool(_mapping(exit_policy).get("withdrawal_paths_visible")) is True
        and bool(_sequence(_mapping(exit_policy).get("rollback_paths")))
    )
    exact_zero_runtime_authority = all(authority_zero_by_phase.values()) and _authority_zero(_mapping(review.get("authority_counters", {})) or zero_authority_counters())

    gates = {
        "distinct_reviewer": bool(reviewer_id and builder_id and reviewer_id != builder_id),
        "independent_review_passed": review_current and review.get("verdict") == "PASS" and review.get("reviewer_id") == reviewer_id,
        "current_upstream_evidence_hashes": all(upstream_hashes_current.values()) and set(upstream_hashes) == {f"p{phase}" for phase in P130_PHASES},
        "upstream_p123_p129_ready": all(upstream_status_ready.values()),
        "traceability_1_0": claim_ledger["traceability_ratio"] == 1.0 and bool(claim_ledger["claims"]),
        "zero_undocumented_or_untraced_claims": claim_ledger["undocumented_claim_count"] == 0 and claim_ledger["untraced_claim_count"] == 0,
        "zero_high_critical_blockers": risk_register["high_critical_open_blockers"] == [],
        "risk_register_complete": risk_register["incomplete_risk_count"] == 0 and bool(risk_register["risks"]),
        "zero_prohibited_claims": claim_ledger["prohibited_claims"] == [],
        "feedback_requires_no_credentials_or_production_access": feedback_safe,
        "exact_zero_runtime_authority": exact_zero_runtime_authority,
        "visible_withdrawal_paths": visible_withdrawal,
    }
    ready = all(gates.values())

    beta_evidence: dict[str, Any] = {
        "schema_version": P130_BETA_EVIDENCE_SCHEMA_VERSION,
        "release_id": "P130-public-beta",
        "scope": "evidence-qualified non-production public beta aggregation",
        "upstream_release_hashes": upstream_hashes,
        "upstream_hashes_current": upstream_hashes_current,
        "upstream_status_ready": upstream_status_ready,
        "input_hashes": input_hashes,
        "claim_ledger_hash": claim_ledger["claim_ledger_hash"],
        "risk_register_hash": risk_register["risk_register_hash"],
        "feedback_intake": feedback,
        "exit_policy": exit_policy,
        "review": {"reviewer_id": reviewer_id, "builder_id": builder_id, "artifact": review},
        "authority": {
            "counters": zero_authority_counters(),
            "upstream_zero_by_phase": authority_zero_by_phase,
            "exact_zero_runtime_authority": exact_zero_runtime_authority,
        },
        "limitations": [
            "Public beta is evidence-qualified and non-production.",
            "Auth, credentials, live connectors, staging mutation, production mutation, production autonomy, and operator replacement are not claimed or enabled.",
            "Reviewer independence is asserted by a distinct process and hash-bound artifact, not cryptographically proven identity.",
        ],
        "withdrawal_paths": _withdrawal_paths(claim_ledger, exit_policy),
        "gates": gates,
        "reasons": [f"{key} failed closed" for key, passed in gates.items() if not passed],
    }
    beta_evidence["beta_evidence_hash"] = stable_hash(beta_evidence)

    release_evidence: dict[str, Any] = {
        "schema_version": P130_RELEASE_EVIDENCE_SCHEMA_VERSION,
        "release_id": "P130-public-beta",
        "release_status": P130_READY_STATUS if ready else P130_BLOCKED_STATUS,
        "product_claim": "Evidence-qualified public beta readiness framework for local, sandbox, replay, and disposable-lab evidence.",
        "public_limitation": (
            "Non-production public beta framework only; auth, credentials, live connectors, staging/production mutation, "
            "production autonomy, and operator replacement are forbidden and unproven. Reviewer independence is process-asserted, not cryptographically proven."
        ),
        "gates": gates,
        "upstream_release_hashes": upstream_hashes,
        "input_hashes": input_hashes,
        "claim_ledger_hash": claim_ledger["claim_ledger_hash"],
        "risk_register_hash": risk_register["risk_register_hash"],
        "beta_evidence_hash": beta_evidence["beta_evidence_hash"],
        "claim_summary": {
            "claim_count": len(claim_ledger["claims"]),
            "traceability_ratio": claim_ledger["traceability_ratio"],
            "undocumented_claim_count": claim_ledger["undocumented_claim_count"],
            "untraced_claim_count": claim_ledger["untraced_claim_count"],
            "prohibited_claims": claim_ledger["prohibited_claims"],
        },
        "risk_summary": {
            "risk_count": len(risk_register["risks"]),
            "incomplete_risk_count": risk_register["incomplete_risk_count"],
            "high_critical_open_blockers": risk_register["high_critical_open_blockers"],
        },
        "authority": {
            "counters": zero_authority_counters(),
            "exact_zero_runtime_authority": exact_zero_runtime_authority,
            "nonzero_phases": [phase for phase, zero in authority_zero_by_phase.items() if not zero],
        },
        "review": {"reviewer_id": reviewer_id, "builder_id": builder_id, "artifact": review},
        "withdrawal_paths": beta_evidence["withdrawal_paths"],
        "reasons": beta_evidence["reasons"],
    }
    release_evidence["release_evidence_hash"] = stable_hash(release_evidence)
    return {
        "claim_ledger": claim_ledger,
        "risk_register": risk_register,
        "beta_evidence": beta_evidence,
        "release_evidence": release_evidence,
    }


def validate_p130_release_evidence(evidence: Mapping[str, Any], *, root: Path = _ROOT) -> dict[str, Any]:
    """Validate a P130 release artifact by rebuilding from local inputs."""

    review = _mapping(evidence.get("review"))
    rebuilt = build_p130_public_beta(
        root=root,
        builder_id=str(review.get("builder_id", "")),
        reviewer_id=str(review.get("reviewer_id", "")),
    )["release_evidence"]
    expected_without_hash = {key: value for key, value in rebuilt.items() if key != "release_evidence_hash"}
    actual_without_hash = {key: value for key, value in evidence.items() if key != "release_evidence_hash"}
    checks = {
        "schema_current": evidence.get("schema_version") == P130_RELEASE_EVIDENCE_SCHEMA_VERSION,
        "self_hash_current": evidence.get("release_evidence_hash") == stable_hash({key: value for key, value in evidence.items() if key != "release_evidence_hash"}),
        "all_fields_current": actual_without_hash == expected_without_hash,
        "upstream_hashes_current": evidence.get("upstream_release_hashes") == rebuilt.get("upstream_release_hashes"),
        "claim_ledger_current": evidence.get("claim_ledger_hash") == rebuilt.get("claim_ledger_hash"),
        "risk_register_current": evidence.get("risk_register_hash") == rebuilt.get("risk_register_hash"),
        "beta_evidence_current": evidence.get("beta_evidence_hash") == rebuilt.get("beta_evidence_hash"),
        "gates_current": evidence.get("gates") == rebuilt.get("gates"),
        "release_qualified": evidence.get("release_status") == P130_READY_STATUS and rebuilt.get("release_status") == P130_READY_STATUS,
    }
    return {"valid": all(checks.values()), "checks": checks, "reasons": [f"{key} failed closed" for key, passed in checks.items() if not passed]}


def _build_claim_ledger(claims: Sequence[Mapping[str, Any]], *, upstream_hashes: Mapping[str, Any]) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    undocumented: list[str] = []
    untraced: list[str] = []
    prohibited: list[str] = []
    missing_withdrawal = 0
    known_phases = set(upstream_hashes)
    for index, raw in enumerate(claims):
        claim = dict(raw)
        claim_id = _nonempty_text(claim.get("claim_id")) or f"claim-{index}"
        evidence = [_mapping(item) for item in _sequence(claim.get("evidence"))]
        evidence_refs = [
            {
                "phase": str(item.get("phase", "")),
                "artifact": str(item.get("artifact", "")),
                "release_evidence_hash": upstream_hashes.get(str(item.get("phase", ""))),
            }
            for item in evidence
        ]
        missing_docs = [
            field
            for field in ("owner", "test", "limitation", "scope", "review_date", "withdrawal_path")
            if not _nonempty_text(claim.get(field))
        ]
        if _nonempty_text(claim.get("status")) not in _CLAIM_STATUSES:
            missing_docs.append("status")
        if missing_docs:
            undocumented.append(claim_id)
        if not evidence_refs or any(not item["release_evidence_hash"] or item["phase"] not in known_phases for item in evidence_refs):
            untraced.append(claim_id)
        if not _nonempty_text(claim.get("withdrawal_path")):
            missing_withdrawal += 1
        if _claim_forbidden(claim):
            prohibited.append(claim_id)
        normalized.append(
            {
                "claim_id": claim_id,
                "statement": str(claim.get("statement", "")),
                "owner": str(claim.get("owner", "")),
                "status": str(claim.get("status", "")),
                "evidence": evidence_refs,
                "test": str(claim.get("test", "")),
                "limitation": str(claim.get("limitation", "")),
                "scope": str(claim.get("scope", "")),
                "review_date": str(claim.get("review_date", "")),
                "withdrawal_path": str(claim.get("withdrawal_path", "")),
            }
        )
    traced = sum(1 for claim in normalized if claim["claim_id"] not in untraced)
    ratio = traced / len(normalized) if normalized else 0.0
    ledger: dict[str, Any] = {
        "schema_version": P130_CLAIM_LEDGER_SCHEMA_VERSION,
        "claims": normalized,
        "traceability_ratio": ratio,
        "undocumented_claim_count": len(set(undocumented)),
        "untraced_claim_count": len(set(untraced)),
        "prohibited_claims": sorted(set(prohibited)),
        "missing_withdrawal_path_count": missing_withdrawal,
    }
    ledger["claim_ledger_hash"] = stable_hash(ledger)
    return ledger


def _build_risk_register(risks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    incomplete: list[str] = []
    blockers: list[str] = []
    for index, raw in enumerate(risks):
        risk = dict(raw)
        risk_id = _nonempty_text(risk.get("risk_id")) or f"risk-{index}"
        missing = [
            field
            for field in ("owner", "mitigation", "residual_risk", "review_date", "stop_or_rollback_condition")
            if not _nonempty_text(risk.get(field))
        ]
        severity = str(risk.get("severity", "")).lower()
        status = str(risk.get("status", "")).lower()
        if severity not in _RISK_SEVERITIES:
            missing.append("severity")
        if not status:
            missing.append("status")
        if missing:
            incomplete.append(risk_id)
        if severity in _BLOCKING_SEVERITIES and status not in _CLOSED_RISK_STATUSES:
            blockers.append(risk_id)
        normalized.append(
            {
                "risk_id": risk_id,
                "description": str(risk.get("description", "")),
                "severity": severity,
                "status": status,
                "owner": str(risk.get("owner", "")),
                "mitigation": str(risk.get("mitigation", "")),
                "residual_risk": str(risk.get("residual_risk", "")),
                "review_date": str(risk.get("review_date", "")),
                "stop_or_rollback_condition": str(risk.get("stop_or_rollback_condition", "")),
            }
        )
    register: dict[str, Any] = {
        "schema_version": P130_RISK_REGISTER_SCHEMA_VERSION,
        "risks": normalized,
        "incomplete_risk_count": len(set(incomplete)),
        "incomplete_risks": sorted(set(incomplete)),
        "high_critical_open_blockers": sorted(set(blockers)),
    }
    register["risk_register_hash"] = stable_hash(register)
    return register


def _review_current(review: Mapping[str, Any], *, reviewer_id: str, builder_id: str, upstream_hashes: Mapping[str, Any]) -> bool:
    if not review or not reviewer_id or not builder_id or reviewer_id == builder_id:
        return False
    if review.get("schema_version") != "p130.independent_review.v1":
        return False
    if review.get("verdict") != "PASS" or review.get("reviewer_id") != reviewer_id or review.get("builder_id") != builder_id:
        return False
    if review.get("review_method") not in {"codex_native_subagent", "ci_signed"}:
        return False
    if _mapping(review.get("reviewed_release_hashes")) != dict(upstream_hashes):
        return False
    return _hash_current(review, "self_hash")


def _claim_forbidden(claim: Mapping[str, Any]) -> bool:
    text = " ".join(str(claim.get(field, "")) for field in ("claim_id", "statement", "scope", "status"))
    return any(pattern.search(text) for pattern in _FORBIDDEN_CLAIM_PATTERNS)


def _feedback_safe(feedback: Mapping[str, Any]) -> bool:
    if not feedback:
        return False
    for key in ("requires_credentials", "requires_production_access", "requires_live_connector"):
        if feedback.get(key) is not False:
            return False
    text = " ".join(str(feedback.get(key, "")) for key in ("support_boundary", "scope", "claim"))
    return not any(pattern.search(text) for pattern in _FORBIDDEN_CLAIM_PATTERNS)


def _withdrawal_paths(claim_ledger: Mapping[str, Any], exit_policy: Mapping[str, Any]) -> list[str]:
    paths = [str(_mapping(claim).get("withdrawal_path", "")) for claim in _sequence(claim_ledger.get("claims")) if str(_mapping(claim).get("withdrawal_path", ""))]
    paths.extend(str(item) for item in _sequence(_mapping(exit_policy).get("rollback_paths")) if str(item))
    return sorted(dict.fromkeys(paths))


def _load_input_records(root: Path, *, schema: str, key: str) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    for path in sorted((root / "evals/p130/input").glob("*.json")):
        payload = _read_json(path)
        if payload.get("schema_version") == schema:
            records.extend(_mapping(item) for item in _sequence(payload.get(key)))
    return records


def _first_input(root: Path, *, schema: str) -> Mapping[str, Any]:
    for path in sorted((root / "evals/p130/input").glob("*.json")):
        payload = _read_json(path)
        if payload.get("schema_version") == schema:
            return payload
    return {}


def _input_hashes(root: Path) -> dict[str, str]:
    base = root / "evals/p130/input"
    hashes: dict[str, str] = {}
    for path in sorted(base.glob("**/*")):
        if path.is_file():
            hashes[path.relative_to(root).as_posix()] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _upstream_ready(evidence: Mapping[str, Any]) -> bool:
    if not evidence:
        return False
    status = str(evidence.get("release_status") or evidence.get("status") or "").lower()
    gates = _mapping(evidence.get("gates"))
    status_ready = any(token in status for token in ("ready", "qualified", "promoted", "local_rc"))
    explicit_gate = gates.get("ready") is True or gates.get("release_ready") is True
    boolean_gates = [value for value in gates.values() if isinstance(value, bool)]
    boolean_gates_pass = bool(boolean_gates) and all(boolean_gates)
    return _hash_current(evidence, "release_evidence_hash") and (status_ready or explicit_gate) and boolean_gates_pass


def _find_authority_counters(value: Mapping[str, Any]) -> Mapping[str, Any]:
    authority = _mapping(value.get("authority"))
    candidates = (
        authority.get("counters"),
        authority.get("production_authority_counters"),
        value.get("authority_counters"),
        value.get("production_authority_counters"),
    )
    for candidate in candidates:
        if isinstance(candidate, Mapping):
            return candidate
    return {}


def _authority_zero(counters: Mapping[str, Any]) -> bool:
    return set(counters) == set(P121_AUTHORITY_COUNTER_KEYS) and all(
        isinstance(counters.get(key), int) and not isinstance(counters.get(key), bool) and counters.get(key) == 0
        for key in P121_AUTHORITY_COUNTER_KEYS
    )


def _evidence_authority_zero(evidence: Mapping[str, Any]) -> bool:
    """Require the exact canonical authority schema; missing or legacy maps fail closed."""

    return _authority_zero(_find_authority_counters(evidence))


def _hash_current(value: Mapping[str, Any], field: str) -> bool:
    return bool(value) and value.get(field) == stable_hash({key: item for key, item in value.items() if key != field})


def _release_hash(evidence: Mapping[str, Any]) -> Any:
    return evidence.get("release_evidence_hash")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, list | tuple) else ()


def _nonempty_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
