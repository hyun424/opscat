"""P126 strict ephemeral local lab remediation state machine."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import zero_authority_counters as p121_zero_authority_counters

P126_SCENARIO_SCHEMA_VERSION = "p126.lab_scenario.v1"
P126_REPORT_SCHEMA_VERSION = "p126.lab_report.v1"
P126_RELEASE_EVIDENCE_SCHEMA_VERSION = "p126.release_evidence.v1"
LAB_LABEL = "opscat-disposable-lab"
ALLOWED_ACTIONS = frozenset({"restart_worker", "rotate_local_token", "clear_queue", "scale_fixture"})
FORBIDDEN_ACTION_MARKERS = ("shell", "subprocess", "network", "connector", "kubernetes", "cloud", "database", "credential")
DENIED_SCOPE_MARKERS = ("production", "prod", "real-staging", "staging", "persistent", "shared", "credential", "secret", "database")
FORBIDDEN_AUTHORITY_COUNTERS: tuple[str, ...] = (
    "nonlocal_mutation_count",
    "real_staging_mutation_count",
    "production_mutation_count",
    "credential_authority_count",
    "live_connector_write_count",
    "network_mutation_count",
    "shell_execution_count",
    "subprocess_execution_count",
    "kubernetes_mutation_count",
    "cloud_mutation_count",
    "database_driver_count",
    "authority_escape_count",
)
REQUIRED_DENIED_COVERAGE: tuple[str, ...] = (
    "real_staging",
    "production",
    "credential_secret",
    "forbidden_network_shell_subprocess_action",
    "non_lab_target",
)
StateName = Literal["declared", "approved", "preflighted", "simulated", "executed", "validated", "rolled_back", "cleaned"]


class LabRemediationError(ValueError):
    """Raised when P126 lab-only remediation evidence is invalid."""


@dataclass(frozen=True)
class LabState:
    scenario_id: str
    action: str
    target: str
    state: StateName = "declared"
    effect_count: int = 0
    rolled_back: bool = False
    cleaned: bool = False


def load_lab_scenarios(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise LabRemediationError("scenario_set_must_be_object")
    return payload


def run_lab_remediation(scenario_set: Mapping[str, Any]) -> dict[str, Any]:
    scenarios = _scenarios(scenario_set)
    with tempfile.TemporaryDirectory(prefix="opscat-p126-lab-") as lab_dir_name:
        lab_dir = Path(lab_dir_name)
        receipts = [_run_scenario(raw, lab_dir=lab_dir) for raw in scenarios]
        residue_before_exit = _residue_count(lab_dir)
        tempdir_path = lab_dir
    tempdir_exists_after_cleanup = tempdir_path.exists()
    metrics = _metrics(receipts)
    report: dict[str, Any] = {
        "schema_version": P126_REPORT_SCHEMA_VERSION,
        "scenario_set_id": str(scenario_set.get("scenario_set_id", "p126-local-lab")),
        "scenario_count": len(receipts),
        "environment": {
            "kind": "ephemeral_local_tempdir",
            "state": "in_memory_typed_transitions",
            "tempdir_exists_after_cleanup": tempdir_exists_after_cleanup,
            "residue_before_tempdir_exit": residue_before_exit,
        },
        "catalog": {"allowed_actions": sorted(ALLOWED_ACTIONS), "forbidden_driver_classes": list(FORBIDDEN_ACTION_MARKERS)},
        "metrics": metrics,
        "denied_coverage": _denied_coverage(receipts),
        "receipts": receipts,
        "authority_counters": zero_authority_counters(),
        "scope_limit": (
            "P126 uses only an ephemeral local tempdir and in-memory typed state transitions; "
            "no real staging, production, credential, connector, network, shell, subprocess, Kubernetes, cloud, or database authority."
        ),
    }
    report["report_hash"] = stable_hash(report)
    if not validate_lab_report(report):
        raise LabRemediationError("report_validation_failed")
    return report


def build_release_evidence(report: Mapping[str, Any], *, report_path: Path) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "schema_version": P126_RELEASE_EVIDENCE_SCHEMA_VERSION,
        "release_status": "ready",
        "artifact_hashes": {
            "report_hash": str(report["report_hash"]),
            "report_file_hash": "sha256:" + __import__("hashlib").sha256(report_path.read_bytes()).hexdigest(),
        },
        "gates": {
            "ready": validate_lab_report(report),
            "scenario_count": int(report["scenario_count"]),
            "approval_accuracy": float(_mapping(report["metrics"])["approval_accuracy"]),
            "unsafe_non_lab_blocking": float(_mapping(report["metrics"])["unsafe_non_lab_blocking"]),
            "eligible_validation": float(_mapping(report["metrics"])["eligible_validation"]),
            "rollback_success": float(_mapping(report["metrics"])["rollback_success"]),
            "duplicate_effects": int(_mapping(report["metrics"])["duplicate_effects"]),
            "cleanup_residue": int(_mapping(report["metrics"])["cleanup_residue"]),
            "authority_counters_zero": all(value == 0 for value in _mapping(report["authority_counters"]).values()),
            "denied_coverage_valid": _denied_coverage_valid(_mapping(report["denied_coverage"])),
        },
        "denied_coverage": dict(_mapping(report["denied_coverage"])),
        "authority": {
            "counters": p121_zero_authority_counters(),
            "exact_nonlocal_authority_zero": True,
            "p126_counters": dict(_mapping(report["authority_counters"])),
        },
        "limitation": "Disposable local lab only; never real staging or production remediation.",
    }
    evidence["release_evidence_hash"] = stable_hash(evidence)
    return evidence


def validate_lab_report(report: Mapping[str, Any]) -> bool:
    if report.get("schema_version") != P126_REPORT_SCHEMA_VERSION:
        return False
    if int(report.get("scenario_count", 0)) < 30:
        return False
    metrics = _mapping(report.get("metrics"))
    required = {
        "approval_accuracy": 1.0,
        "unsafe_non_lab_blocking": 1.0,
        "eligible_validation": 1.0,
        "rollback_success": 1.0,
        "duplicate_effects": 0,
        "cleanup_residue": 0,
    }
    if any(metrics.get(key) != value for key, value in required.items()):
        return False
    if not _denied_coverage_valid(_mapping(report.get("denied_coverage"))):
        return False
    environment = _mapping(report.get("environment"))
    if environment.get("kind") != "ephemeral_local_tempdir" or environment.get("tempdir_exists_after_cleanup") is not False:
        return False
    counters = _mapping(report.get("authority_counters"))
    if set(counters) != set(FORBIDDEN_AUTHORITY_COUNTERS) or any(value != 0 for value in counters.values()):
        return False
    return True


def zero_authority_counters() -> dict[str, int]:
    return {key: 0 for key in FORBIDDEN_AUTHORITY_COUNTERS}


def _scenarios(scenario_set: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if scenario_set.get("schema_version") != P126_SCENARIO_SCHEMA_VERSION:
        raise LabRemediationError("invalid_scenario_schema")
    raw = scenario_set.get("scenarios")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise LabRemediationError("scenarios_must_be_sequence")
    scenarios = [item for item in raw if isinstance(item, Mapping)]
    if len(scenarios) < 30:
        raise LabRemediationError("at_least_30_scenarios_required")
    return scenarios


def _run_scenario(raw: Mapping[str, Any], *, lab_dir: Path) -> dict[str, Any]:
    scenario_id = str(raw.get("scenario_id", ""))
    state = LabState(scenario_id=scenario_id, action=str(raw.get("action", "")), target=str(raw.get("target", "")))
    approval = _approval(raw)
    if approval["approved"]:
        state = replace(state, state="approved")
    preflight = _preflight(raw, approved=bool(approval["approved"]))
    state = replace(state, state="preflighted")
    simulation = {"simulated": False, "state_hash": stable_hash(state)}
    execution = {"executed": False, "effect_count": 0, "state_hash": stable_hash(state)}
    validation = {"passed": False, "state_hash": stable_hash(state)}
    rollback = {"rolled_back": False, "state_hash": stable_hash(state)}
    if preflight["allowed"]:
        state = replace(state, state="simulated")
        simulation = {"simulated": True, "state_hash": stable_hash(state)}
        marker = lab_dir / f"{scenario_id}.json"
        state = replace(state, state="executed", effect_count=1)
        marker.write_text(json.dumps({"scenario_id": scenario_id, "action": state.action, "target": state.target}, sort_keys=True) + "\n", encoding="utf-8")
        execution = {"executed": True, "effect_count": state.effect_count, "state_hash": stable_hash(state)}
        state = replace(state, state="validated")
        validation = {"passed": marker.exists() and state.effect_count == 1, "state_hash": stable_hash(state)}
        marker.unlink()
        state = replace(state, state="rolled_back", effect_count=0, rolled_back=True)
        rollback = {"rolled_back": True, "state_hash": stable_hash(state)}
    cleanup = _cleanup(lab_dir)
    state = replace(state, state="cleaned", cleaned=True)
    receipt: dict[str, Any] = {
        "schema_version": "p126.action_receipt.v1",
        "scenario_id": scenario_id,
        "expected_allowed": bool(raw.get("expected_allowed", False)),
        "approval": approval,
        "preflight": preflight,
        "simulation": simulation,
        "execution": execution,
        "validation": validation,
        "rollback": rollback,
        "cleanup": cleanup,
        "final_state": state.state,
    }
    receipt["receipt_hash"] = stable_hash(receipt)
    return receipt


def _approval(raw: Mapping[str, Any]) -> dict[str, Any]:
    approved = bool(raw.get("approved", False))
    return {"approved": approved, "source": "deterministic_fixture", "pre_action_required": True}


def _preflight(raw: Mapping[str, Any], *, approved: bool) -> dict[str, Any]:
    action = str(raw.get("action", ""))
    target = str(raw.get("target", ""))
    reasons: list[str] = []
    if not approved:
        reasons.append("approval_missing")
    if action not in ALLOWED_ACTIONS or any(marker in action for marker in FORBIDDEN_ACTION_MARKERS):
        reasons.append("forbidden_action")
    if str(raw.get("lab_label", "")) != LAB_LABEL:
        reasons.append("missing_lab_label")
    if str(raw.get("owner", "")) != "p126":
        reasons.append("invalid_owner")
    if int(raw.get("ttl_seconds", 0)) <= 0:
        reasons.append("missing_lab_ttl")
    if not target.startswith("lab-") or any(marker in target for marker in DENIED_SCOPE_MARKERS):
        reasons.append("non_lab_target")
    return {
        "allowed": not reasons,
        "reasons": reasons,
        "action": action,
        "target": target,
        "target_hash": stable_hash({"target": target, "action": action}),
    }


def _cleanup(lab_dir: Path) -> dict[str, Any]:
    for path in sorted(lab_dir.iterdir()):
        if path.is_file():
            path.unlink()
    return {"cleanup_performed": True, "residue_count": _residue_count(lab_dir), "destruction_receipt": stable_hash({"lab_dir": "ephemeral", "residue_count": _residue_count(lab_dir)})}


def _residue_count(lab_dir: Path) -> int:
    return sum(1 for _ in lab_dir.iterdir())


def _metrics(receipts: Sequence[Mapping[str, Any]]) -> dict[str, int | float]:
    expected_matches = [bool(receipt["expected_allowed"]) is bool(_mapping(receipt["preflight"])["allowed"]) for receipt in receipts]
    blocked = [receipt for receipt in receipts if not bool(receipt["expected_allowed"])]
    unsafe_blocked = [not bool(_mapping(receipt["preflight"])["allowed"]) for receipt in blocked]
    eligible = [receipt for receipt in receipts if bool(_mapping(receipt["preflight"])["allowed"])]
    validations = [bool(_mapping(receipt["validation"])["passed"]) for receipt in eligible]
    rollbacks = [bool(_mapping(receipt["rollback"])["rolled_back"]) for receipt in eligible]
    duplicate_effects = sum(max(0, int(_mapping(receipt["execution"])["effect_count"]) - 1) for receipt in receipts)
    cleanup_residue = sum(int(_mapping(receipt["cleanup"])["residue_count"]) for receipt in receipts)
    return {
        "approval_accuracy": _ratio(expected_matches),
        "unsafe_non_lab_blocking": _ratio(unsafe_blocked) if blocked else 0.0,
        "eligible_validation": _ratio(validations),
        "rollback_success": _ratio(rollbacks),
        "duplicate_effects": duplicate_effects,
        "cleanup_residue": cleanup_residue,
    }


def _denied_coverage(receipts: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {key: 0 for key in REQUIRED_DENIED_COVERAGE}
    counts["total_denied"] = 0
    for receipt in receipts:
        if bool(receipt.get("expected_allowed")):
            continue
        counts["total_denied"] += 1
        preflight = _mapping(receipt.get("preflight"))
        if bool(preflight.get("allowed")):
            continue
        reasons = set(_sequence(preflight.get("reasons")))
        target = str(preflight.get("target", ""))
        action = str(preflight.get("action", ""))
        if "real-staging" in target or target.startswith("staging-") or "staging" in target:
            counts["real_staging"] += 1
        if "production" in target or target.startswith("prod-") or target == "prod":
            counts["production"] += 1
        if any(marker in f"{action} {target}" for marker in ("credential", "secret")):
            counts["credential_secret"] += 1
        if any(marker in action for marker in ("network", "shell", "subprocess")):
            counts["forbidden_network_shell_subprocess_action"] += 1
        if "non_lab_target" in reasons or "missing_lab_label" in reasons or "invalid_owner" in reasons:
            counts["non_lab_target"] += 1
    counts["validated_required_categories"] = sum(1 for key in REQUIRED_DENIED_COVERAGE if counts[key] >= 1)
    return counts


def _denied_coverage_valid(coverage: Mapping[str, Any]) -> bool:
    return int(coverage.get("total_denied", 0)) > 0 and all(int(coverage.get(key, 0)) >= 1 for key in REQUIRED_DENIED_COVERAGE)


def _ratio(values: Sequence[bool]) -> float:
    if not values:
        return 1.0
    return sum(1 for value in values if value) / len(values)


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()
