#!/usr/bin/env python3
"""Generate deterministic P134 observation-authority release artifacts."""

from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p110_evaluation import stable_hash  # noqa: E402
from app.services.p134_observation_authority import (  # noqa: E402
    P134AuthorityError,
    build_contract,
    build_contract_core,
    build_proposal,
    build_review_receipt,
    evaluate_proposal,
    new_receipt_ledger,
    validate_contract,
    validate_receipt_ledger,
)
from app.services.p134_release_evidence import (  # noqa: E402
    EXPECTED_DENIAL_REASONS,
    EXPECTED_FAULT_ERRORS,
    P134_READY_STATUS,
    REQUIRED_CONTRACT_CASES,
    REQUIRED_FAULT_CASES,
    P134ReleaseEvidenceError,
    build_authority_ledger,
    build_p134_release_evidence,
    validate_authority_ledger,
    validate_independent_review_artifact,
    validate_p134_release_evidence,
)

PROFILE_SCHEMA_VERSION = "p134.authority_profile.v1"
CONTRACT_MATRIX_SCHEMA_VERSION = "p134.contract_matrix.v1"
FAULT_MATRIX_SCHEMA_VERSION = "p134.fault_matrix.v1"
RESOURCE_LIMITS = {
    "wall_limit_ms": 20_000,
    "cpu_limit_ms": 10_000,
    "peak_memory_limit_bytes": 67_108_864,
}
PROFILE_FIELDS = frozenset(
    {
        "schema_version",
        "contract_core",
        "review",
        "window_started_at",
        "required_contract_cases",
        "required_fault_cases",
        "resource_limits",
    }
)
CORE_INPUT_FIELDS = frozenset(
    {
        "contract_id",
        "contract_version",
        "subject_ref_hash",
        "max_authority_level",
        "allowed_hosts",
        "allowed_methods",
        "allowed_capabilities",
        "budgets",
        "valid_from",
        "expires_at",
        "default_decision",
        "kill_switch",
        "action_authority",
    }
)
REVIEW_INPUT_FIELDS = frozenset({"decision", "reviewer_ref_hash", "reviewed_at", "expires_at"})


def main(argv: Sequence[str] | None = None) -> int:
    started_wall = time.monotonic()
    started_cpu = _cpu_ms()
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, default=ROOT / "evals/p134/input/authority-profile.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evals/p134")
    parser.add_argument("--independent-review", type=Path, default=ROOT / "evals/p134/independent-review.json")
    args = parser.parse_args(argv)

    try:
        profile = _read_json(args.profile)
        profile = _validate_profile(profile)
        contract = _contract_from_profile(profile)
        independent_review = _read_json(args.independent_review)
        validate_independent_review_artifact(
            _mapping(independent_review, "independent_review"),
            expected_source_hashes=_source_hashes(),
        )
        contract_matrix, canonical_ledger = _run_contract_matrix(
            contract=contract,
            profile=profile,
        )
        fault_matrix = _run_fault_matrix(contract, profile)
        authority_ledger = build_authority_ledger(
            evaluator_activity={
                "runner_invocation_count": 1,
                "profile_read_count": 1,
                "artifact_write_count": 5,
            }
        )
        validate_receipt_ledger(canonical_ledger, contract=contract)
        validate_authority_ledger(authority_ledger)
        contract_matrix["resource_usage"] = _resource_usage(
            started_wall=started_wall,
            started_cpu=started_cpu,
        )
        contract_matrix["contract_matrix_hash"] = stable_hash(
            {key: value for key, value in contract_matrix.items() if key != "contract_matrix_hash"}
        )
        release_evidence = build_p134_release_evidence(
            contract_matrix,
            fault_matrix,
            canonical_ledger,
            authority_ledger,
            _mapping(independent_review, "independent_review"),
            project_root=ROOT,
        )
        validate_p134_release_evidence(
            release_evidence,
            contract_matrix=contract_matrix,
            fault_matrix=fault_matrix,
            receipt_ledger=canonical_ledger,
            authority_ledger=authority_ledger,
            independent_review=_mapping(independent_review, "independent_review"),
            project_root=ROOT,
        )
        artifacts = {
            "contract-matrix.json": contract_matrix,
            "fault-matrix.json": fault_matrix,
            "receipt-ledger.json": canonical_ledger,
            "authority-ledger.json": authority_ledger,
            "release-evidence.json": release_evidence,
        }
        _write_exact_artifacts(args.output_dir, artifacts)
        print(
            json.dumps(
                {
                    "release_status": release_evidence["release_status"],
                    "release_evidence_hash": release_evidence["release_evidence_hash"],
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0 if release_evidence["release_status"] == P134_READY_STATUS else 1
    except Exception as exc:
        print(
            json.dumps(
                {
                    "release_status": "p134_blocked",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


def _validate_profile(value: Any) -> Mapping[str, Any]:
    profile = _mapping(value, "profile")
    _expect_fields(profile, PROFILE_FIELDS, "profile")
    if profile.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise ValueError("invalid_profile_schema")
    contract_core = _mapping(profile.get("contract_core"), "contract_core")
    review = _mapping(profile.get("review"), "review")
    limits = _mapping(profile.get("resource_limits"), "resource_limits")
    _expect_fields(contract_core, CORE_INPUT_FIELDS, "contract_core")
    _expect_fields(review, REVIEW_INPUT_FIELDS, "review")
    if profile.get("required_contract_cases") != list(REQUIRED_CONTRACT_CASES):
        raise ValueError("required_contract_cases_mismatch")
    if profile.get("required_fault_cases") != list(REQUIRED_FAULT_CASES):
        raise ValueError("required_fault_cases_mismatch")
    if dict(limits) != RESOURCE_LIMITS:
        raise ValueError("resource_limits_mismatch")
    if not isinstance(profile.get("window_started_at"), str):
        raise ValueError("invalid_window_started_at")
    return profile


def _contract_from_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    core = build_contract_core(_mapping(profile["contract_core"], "contract_core"))
    review = build_review_receipt(core, _mapping(profile["review"], "review"))
    contract = build_contract(core, review)
    validate_contract(contract)
    return contract


def _run_contract_matrix(
    *,
    contract: dict[str, Any],
    profile: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    cases: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_CONTRACT_CASES:
        cases[name] = _run_contract_case(name, contract, profile)
    canonical_ledger = _canonical_receipt_ledger(contract, str(profile["window_started_at"]))
    matrix: dict[str, Any] = {
        "schema_version": CONTRACT_MATRIX_SCHEMA_VERSION,
        "required_cases": list(REQUIRED_CONTRACT_CASES),
        "cases": cases,
        "totals": {
            "expected_cases": 18,
            "passed_cases": sum(1 for case in cases.values() if case["passed"] is True),
            "failed_cases": sum(1 for case in cases.values() if case["passed"] is not True),
            "allowed_cases": sum(1 for case in cases.values() if case["outcome"] == "allowed"),
            "denied_cases": sum(1 for case in cases.values() if case["outcome"] == "denied"),
            "duplicate_cases": sum(1 for case in cases.values() if case["duplicate"] is True),
            "denominator_scope": "principal_contract_assertions",
        },
        "canonical_contract": deepcopy(contract),
        "resource_usage": {
            "wall_time_ms": 0,
            "cpu_time_ms": 0,
            "peak_memory_bytes": 0,
            **RESOURCE_LIMITS,
        },
    }
    matrix["contract_matrix_hash"] = stable_hash(matrix)
    return matrix, canonical_ledger


def _run_contract_case(name: str, contract: dict[str, Any], profile: Mapping[str, Any]) -> dict[str, Any]:
    if name == "oa0_default_deny":
        result = _evaluate_once(_contract_variant(contract, max_authority_level="OA0_CONTRACT_ONLY"), profile, name)
        return _case_from_receipt(result.receipt, expected_reason=EXPECTED_DENIAL_REASONS[name])
    if name == "oa1_allowed":
        result = _evaluate_once(contract, profile, name)
        return _case_from_receipt(result.receipt, expected_decision="allowed")
    if name == "deterministic_duplicate":
        first = _evaluate_once(contract, profile, name)
        duplicate = evaluate_proposal(contract, first.receipt["proposal"], first.ledger)
        return _case(
            outcome="duplicate",
            decision=duplicate.receipt["decision"],
            reasons=list(duplicate.receipt["reasons"]),
            duplicate=duplicate.duplicate,
            ledger_unchanged=duplicate.ledger == first.ledger,
            passed=duplicate.duplicate is True
            and duplicate.ledger == first.ledger
            and duplicate.receipt == first.receipt
            and duplicate.receipt["decision"] == "allowed",
        )
    if name == "capability_denied":
        result = _evaluate_once(contract, profile, name, capability="telemetry.topology.read")
    elif name == "host_denied":
        result = _evaluate_once(contract, profile, name, host_label="local-artifact.unlisted")
    elif name == "method_denied":
        result = _evaluate_once(contract, profile, name, method="HTTP_GET")
    elif name == "level_escalation_denied":
        result = _evaluate_once(contract, profile, name, requested_level="OA2_PROVIDER_SHAPED_LOCAL_EXPORT")
    elif name == "kill_switch_deny":
        result = _evaluate_once(_contract_variant(contract, kill_switch=True), profile, name)
    elif name == "contract_not_yet_valid":
        future_contract = _contract_variant(
            contract,
            valid_from="2026-07-13T00:30:00Z",
            expires_at="2026-07-13T03:00:00Z",
            reviewed_at="2026-07-13T00:30:01Z",
            review_expires_at="2026-07-13T02:59:59Z",
        )
        result = _evaluate_once(future_contract, profile, name, proposed_at="2026-07-13T00:10:00Z")
    elif name == "contract_expired":
        expired_contract = _contract_variant(
            contract,
            expires_at="2026-07-13T00:30:00Z",
            reviewed_at="2026-07-13T00:00:01Z",
            review_expires_at="2026-07-13T00:29:59Z",
        )
        result = _evaluate_once(expired_contract, profile, name, proposed_at="2026-07-13T00:40:00Z")
    elif name == "allowed_request_budget_exhausted":
        result = _budget_exhaustion_case(contract, profile, name, "request")
    elif name == "byte_budget_exhausted":
        result = _budget_exhaustion_case(contract, profile, name, "byte")
    elif name == "record_budget_exhausted":
        result = _budget_exhaustion_case(contract, profile, name, "record")
    elif name == "host_budget_exhausted":
        result = _budget_exhaustion_case(contract, profile, name, "host")
    elif name == "capability_budget_exhausted":
        result = _budget_exhaustion_case(contract, profile, name, "capability")
    elif name == "response_byte_estimate_too_large":
        result = _evaluate_once(
            contract,
            profile,
            name,
            estimated_response_bytes=_over_contract_limit(contract, "max_single_response_bytes", 67_108_864),
        )
    elif name == "timeout_too_large":
        result = _evaluate_once(contract, profile, name, timeout_ms=_over_contract_limit(contract, "max_timeout_ms", 60_000))
    elif name == "attempt_budget_exhausted":
        result = _evaluate_once(contract, profile, name, attempt_number=_over_contract_limit(contract, "max_attempt_number", 10))
    else:
        raise ValueError(f"unknown_contract_case:{name}")
    return _case_from_receipt(result.receipt, expected_reason=EXPECTED_DENIAL_REASONS[name])


def _run_fault_matrix(contract: dict[str, Any], profile: Mapping[str, Any]) -> dict[str, Any]:
    cases = {name: _run_fault_case(name, contract, profile) for name in REQUIRED_FAULT_CASES}
    matrix: dict[str, Any] = {
        "schema_version": FAULT_MATRIX_SCHEMA_VERSION,
        "required_cases": list(REQUIRED_FAULT_CASES),
        "cases": cases,
        "totals": {
            "expected_cases": 6,
            "passed_cases": sum(1 for case in cases.values() if case["passed"] is True),
            "failed_cases": sum(1 for case in cases.values() if case["passed"] is not True),
            "rejected_cases": sum(1 for case in cases.values() if case["outcome"] == "rejected"),
            "denominator_scope": "principal_fault_assertions",
        },
    }
    matrix["fault_matrix_hash"] = stable_hash(matrix)
    return matrix


def _run_fault_case(name: str, contract: dict[str, Any], profile: Mapping[str, Any]) -> dict[str, Any]:
    ledger = new_receipt_ledger(contract, window_started_at=str(profile["window_started_at"]))
    before = deepcopy(ledger)
    try:
        if name == "tampered_review_receipt":
            tampered = deepcopy(contract)
            tampered["review_receipt"]["decision"] = "reject"
            tampered["contract_hash"] = stable_hash(
                {key: value for key, value in tampered.items() if key != "contract_hash"}
            )
            evaluate_proposal(tampered, _proposal(contract, name, 1), ledger)
        elif name == "changed_request_id_replay":
            result = evaluate_proposal(contract, _proposal(contract, name, 1), ledger)
            hosts = _allowed_sequence(contract, "allowed_hosts", minimum=2)
            changed = _proposal(contract, name, 1, host_label=hosts[1])
            evaluate_proposal(contract, changed, result.ledger)
        elif name == "boolean_counter_rejected":
            tampered_ledger = deepcopy(ledger)
            tampered_ledger["counters"]["evaluated_count"] = False
            tampered_ledger["ledger_hash"] = stable_hash(
                {key: value for key, value in tampered_ledger.items() if key != "ledger_hash"}
            )
            evaluate_proposal(contract, _proposal(contract, name, 1), tampered_ledger)
        elif name == "url_credential_input_rejected":
            build_proposal(_proposal_input(contract, "url-shaped-input", 1, host_label="https://token.example"))
        elif name == "ledger_reorder_rejected":
            first = evaluate_proposal(contract, _proposal(contract, name, 1), ledger)
            second = evaluate_proposal(contract, _proposal(contract, f"{name}-two", 2), first.ledger)
            reordered = deepcopy(second.ledger)
            reordered["receipts"] = [reordered["receipts"][1], reordered["receipts"][0]]
            reordered["ledger_hash"] = stable_hash(
                {key: value for key, value in reordered.items() if key != "ledger_hash"}
            )
            validate_receipt_ledger(reordered, contract=contract)
        elif name == "nonzero_action_authority_rejected":
            tampered = deepcopy(contract)
            tampered["core"]["action_authority"]["production_mutation_count"] = 1
            tampered["core"]["core_hash"] = stable_hash(
                {key: value for key, value in tampered["core"].items() if key != "core_hash"}
            )
            tampered["review_receipt"] = build_review_receipt(tampered["core"], _review_input(profile))
            tampered["contract_hash"] = stable_hash(
                {key: value for key, value in tampered.items() if key != "contract_hash"}
            )
            validate_contract(tampered)
        else:
            raise ValueError(f"unknown_fault_case:{name}")
    except (P134AuthorityError, P134ReleaseEvidenceError, ValueError) as exc:
        error = str(exc)
        return _case(
            outcome="rejected",
            decision=None,
            error=error,
            ledger_unchanged=ledger == before,
            passed=error == EXPECTED_FAULT_ERRORS[name] and ledger == before,
        )
    return _case(outcome="accepted", decision=None, error=None, passed=False)


def _canonical_receipt_ledger(contract: dict[str, Any], window_started_at: str) -> dict[str, Any]:
    ledger = new_receipt_ledger(contract, window_started_at=window_started_at)
    hosts = _allowed_sequence(contract, "allowed_hosts", minimum=2)
    methods = _allowed_sequence(contract, "allowed_methods", minimum=2)
    capabilities = _allowed_sequence(contract, "allowed_capabilities", minimum=2)
    for sequence, (host, method, capability) in enumerate(
        (
            (hosts[0], methods[0], capabilities[0]),
            (hosts[1], methods[1], capabilities[1]),
        ),
        start=1,
    ):
        result = evaluate_proposal(
            contract,
            _proposal(
                contract,
                f"canonical-{sequence}",
                sequence,
                proposed_at=f"2026-07-13T00:{10 + sequence:02d}:00Z",
                host_label=host,
                method=method,
                capability=capability,
                estimated_response_bytes=100 * sequence,
                estimated_records=10 * sequence,
            ),
            ledger,
        )
        ledger = result.ledger
    return ledger


def _budget_exhaustion_case(
    contract: dict[str, Any],
    profile: Mapping[str, Any],
    name: str,
    budget: str,
) -> Any:
    variant = contract
    if budget == "request":
        variant = _contract_variant(contract, budgets={"max_allowed_requests_per_window": 1})
        first = _evaluate_once(variant, profile, f"{name}-pre", sequence=1)
        return evaluate_proposal(variant, _proposal(variant, name, 2), first.ledger)
    if budget == "byte":
        variant = _contract_variant(
            contract,
            budgets={
                "max_allowed_estimated_response_bytes_per_window": 150,
                "max_single_response_bytes": 150,
            },
        )
        first = _evaluate_once(variant, profile, f"{name}-pre", sequence=1, estimated_response_bytes=100)
        return evaluate_proposal(variant, _proposal(variant, name, 2, estimated_response_bytes=100), first.ledger)
    if budget == "record":
        variant = _contract_variant(contract, budgets={"max_allowed_estimated_records_per_window": 15})
        first = _evaluate_once(variant, profile, f"{name}-pre", sequence=1, estimated_records=10)
        return evaluate_proposal(variant, _proposal(variant, name, 2, estimated_records=10), first.ledger)
    if budget == "host":
        variant = _contract_variant(contract, budgets={"max_unique_hosts_per_window": 1})
        hosts = _allowed_sequence(variant, "allowed_hosts", minimum=2)
        first = _evaluate_once(variant, profile, f"{name}-pre", sequence=1, host_label=hosts[0])
        return evaluate_proposal(variant, _proposal(variant, name, 2, host_label=hosts[1]), first.ledger)
    if budget == "capability":
        variant = _contract_variant(contract, budgets={"max_unique_capabilities_per_window": 1})
        capabilities = _allowed_sequence(variant, "allowed_capabilities", minimum=2)
        first = _evaluate_once(variant, profile, f"{name}-pre", sequence=1, capability=capabilities[0])
        return evaluate_proposal(
            variant,
            _proposal(variant, name, 2, capability=capabilities[1]),
            first.ledger,
        )
    raise ValueError(f"unknown_budget:{budget}")


def _evaluate_once(
    contract: dict[str, Any],
    profile: Mapping[str, Any],
    request_id: str,
    *,
    sequence: int = 1,
    **overrides: Any,
) -> Any:
    ledger = new_receipt_ledger(contract, window_started_at=str(profile["window_started_at"]))
    return evaluate_proposal(contract, _proposal(contract, request_id, sequence, **overrides), ledger)


def _proposal(contract: dict[str, Any], request_id: str, sequence: int, **overrides: Any) -> dict[str, Any]:
    return build_proposal(_proposal_input(contract, request_id, sequence, **overrides))


def _proposal_input(contract: dict[str, Any], request_id: str, sequence: int, **overrides: Any) -> dict[str, Any]:
    core = _mapping(contract["core"], "contract_core")
    hosts = list(core["allowed_hosts"])
    methods = list(core["allowed_methods"])
    capabilities = list(core["allowed_capabilities"])
    data: dict[str, Any] = {
        "request_id": request_id,
        "sequence": sequence,
        "proposed_at": "2026-07-13T00:10:00Z",
        "requested_level": "OA1_LOCAL_ARTIFACT",
        "source_ref_hash": stable_hash({"source": request_id}),
        "host_label": hosts[0] if hosts else "local-artifact.contract",
        "method": methods[0] if methods else "LOCAL_STAT",
        "capability": capabilities[0] if capabilities else "telemetry.metadata.read",
        "estimated_response_bytes": 100,
        "estimated_records": 10,
        "timeout_ms": 1_000,
        "attempt_number": 1,
    }
    data.update(overrides)
    return data


def _allowed_sequence(contract: dict[str, Any], field: str, *, minimum: int) -> list[str]:
    values = list(_mapping(contract["core"], "contract_core")[field])
    if len(values) < minimum:
        raise ValueError(f"{field}_requires_at_least_{minimum}")
    return values


def _over_contract_limit(contract: dict[str, Any], budget_key: str, global_maximum: int) -> int:
    budget = _mapping(_mapping(contract["core"], "contract_core")["budgets"], "budgets")
    value = budget[budget_key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"invalid_budget:{budget_key}")
    if value >= global_maximum:
        raise ValueError(f"{budget_key}_must_leave_adversarial_headroom")
    return value + 1


def _contract_variant(contract: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    core_input = {
        key: deepcopy(value)
        for key, value in _mapping(contract["core"], "contract_core").items()
        if key not in {"schema_version", "core_hash"}
    }
    review_input = {
        key: deepcopy(value)
        for key, value in _mapping(contract["review_receipt"], "review_receipt").items()
        if key
        in {
            "decision",
            "reviewer_ref_hash",
            "reviewed_at",
            "expires_at",
        }
    }
    budgets = dict(core_input["budgets"])
    budgets.update(overrides.pop("budgets", {}))
    core_input["budgets"] = budgets
    if "reviewed_at" in overrides:
        review_input["reviewed_at"] = overrides.pop("reviewed_at")
    if "review_expires_at" in overrides:
        review_input["expires_at"] = overrides.pop("review_expires_at")
    if "max_authority_level" in overrides and overrides["max_authority_level"] == "OA0_CONTRACT_ONLY":
        core_input["allowed_hosts"] = []
        core_input["allowed_methods"] = []
        core_input["allowed_capabilities"] = []
    core_input.update(overrides)
    core = build_contract_core(core_input)
    review = build_review_receipt(core, review_input)
    return build_contract(core, review)


def _review_input(profile: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(profile["review"], "review")


def _case_from_receipt(
    receipt: Mapping[str, Any],
    *,
    expected_decision: str | None = None,
    expected_reason: str | None = None,
) -> dict[str, Any]:
    decision = receipt["decision"]
    reasons = list(receipt["reasons"])
    if expected_decision == "allowed":
        return _case(
            outcome="allowed",
            decision=str(decision),
            reasons=reasons,
            passed=decision == "allowed" and not reasons,
        )
    return _case(
        outcome="denied",
        decision=str(decision),
        reasons=reasons,
        passed=decision == "denied" and expected_reason in reasons,
    )


def _case(
    *,
    outcome: str,
    decision: str | None,
    reasons: list[str] | None = None,
    duplicate: bool = False,
    ledger_unchanged: bool = False,
    error: str | None = None,
    passed: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "passed": passed,
        "outcome": outcome,
        "decision": decision,
        "reasons": reasons or [],
        "duplicate": duplicate,
        "ledger_unchanged": ledger_unchanged,
        "error": error,
    }
    payload["case_hash"] = stable_hash(payload)
    return payload


def _source_hashes() -> dict[str, str]:
    from app.services.p134_release_evidence import current_source_hashes

    return current_source_hashes(ROOT)


def _resource_usage(*, started_wall: float, started_cpu: int) -> dict[str, int]:
    return {
        "wall_time_ms": max(0, int((time.monotonic() - started_wall) * 1000)),
        "cpu_time_ms": max(0, _cpu_ms() - started_cpu),
        "peak_memory_bytes": _peak_memory_bytes(),
        **RESOURCE_LIMITS,
    }


def _cpu_ms() -> int:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return int((usage.ru_utime + usage.ru_stime) * 1000)


def _peak_memory_bytes() -> int:
    usage = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform == "darwin":
        return usage
    return usage * 1024


def _read_json(path: Path) -> Any:
    return json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))


def _write_exact_artifacts(output_dir: Path, artifacts: Mapping[str, Mapping[str, Any]]) -> None:
    if set(artifacts) != {
        "contract-matrix.json",
        "fault-matrix.json",
        "receipt-ledger.json",
        "authority-ledger.json",
        "release-evidence.json",
    }:
        raise ValueError("artifact_set_invalid")
    target_dir = output_dir.expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    staged: list[tuple[Path, Path]] = []
    try:
        for name, payload in artifacts.items():
            target = target_dir / name
            temporary = target_dir / f".{name}.tmp"
            temporary.write_text(_canonical_json(payload), encoding="utf-8")
            staged.append((temporary, target))
        for temporary, target in staged:
            temporary.replace(target)
    finally:
        for temporary, _target in staged:
            if temporary.exists():
                temporary.unlink()


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True) + "\n"


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"invalid_{label}")
    return value


def _expect_fields(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = {str(key) for key in value}
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        if missing:
            raise ValueError(f"missing_{label}_field:{missing[0]}")
        raise ValueError(f"unexpected_{label}_field:{extra[0]}")


if __name__ == "__main__":
    raise SystemExit(main())
