"""Deterministic P174 live-lab qualification harness.

The engine is intentionally transport-agnostic: callers inject typed observer
and action clients, and this module only validates manifests, schedules the
fixed gates, scores returned facts, and writes hash-bound evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol

MANIFEST_SCHEMA_VERSION = "p174.live_harness_manifest.v1"
SUMMARY_SCHEMA_VERSION = "p174.live_harness_summary.v1"
EVIDENCE_SCHEMA_VERSION = "p174.live_harness_evidence.v1"
HEALTHY_WINDOW_GATE = 200
SCENARIO_CAMPAIGN_GATE = 100
MAX_BASELINE_STABILIZATION_ATTEMPTS = 20
MIN_HEALTHY_WINDOW_DELTA_SECONDS = 14
GENESIS_HASH = "sha256:" + ("0" * 64)
CAMPAIGN_DISTRIBUTION = {
    "restart_recovery": 25,
    "canary_rollback": 25,
    "rejection": 20,
    "rollback_required": 20,
    "safety_boundary": 10,
}

_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_FORBIDDEN_TEXT_RE = re.compile(
    r"(?:https?://|wss?://|://|`|\$\(|\$\{|;|&&|\|\||\b(?:bash|curl|gcloud|host|kubectl|metadata|password|prod|production|rm\s+-rf|secret|shell|ssh|terraform|token|url|wget)\b)",
    re.IGNORECASE,
)
_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "manifest_id",
        "reviewed",
        "reviewed_by",
        "reviewed_at",
        "lab_id",
        "seed",
        "observer_contract_hash",
        "action_contract_hash",
        "allowed_targets",
        "allowed_actions",
        "notes",
    }
)

GateKind = Literal["healthy_window", "scenario_campaign"]
ScenarioKind = Literal["restart_recovery", "canary_rollback", "rejection", "rollback_required", "safety_boundary"]
ExpectedOutcome = Literal["applied", "rejected", "rolled_back", "blocked_no_mutation", "failed_closed"]

_PROTECTED_STATE_FIELDS = (
    "project_id",
    "target_id",
    "run_id",
    "pool_size",
    "canary_version",
    "worker_restart_generation",
    "worker_paused_until",
)


class P174LiveHarnessError(ValueError):
    """Raised when P174 live-harness input cannot be qualified safely."""


class ObserverClient(Protocol):
    def observe_health_window(self, step: ScheduleStep) -> Mapping[str, Any]: ...

    def observe_scenario(self, step: ScenarioStep) -> Mapping[str, Any]: ...


class ActionClient(Protocol):
    def inject_fault(self, step: ScenarioStep, baseline: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def run_scenario(self, step: ScenarioStep, baseline: Mapping[str, Any], fault_result: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def cleanup_scenario(self, step: ScenarioStep, baseline: Mapping[str, Any], post_result: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class ReviewedManifest:
    schema_version: str
    manifest_id: str
    manifest_hash: str
    reviewed: bool
    reviewed_by: str
    reviewed_at: str
    lab_id: str
    seed: int
    observer_contract_hash: str
    action_contract_hash: str
    allowed_targets: tuple[str, ...]
    allowed_actions: tuple[str, ...]


@dataclass(frozen=True)
class ScheduleStep:
    gate: GateKind
    index: int
    target: str
    action: str
    schedule_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "index": self.index,
            "target": self.target,
            "action": self.action,
            "schedule_hash": self.schedule_hash,
        }


@dataclass(frozen=True)
class ScenarioDefinition:
    name: ScenarioKind
    fault: str
    action: str
    expected_outcome: ExpectedOutcome

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.name,
            "fault": self.fault,
            "action": self.action,
            "expected_outcome": self.expected_outcome,
        }


@dataclass(frozen=True)
class ScenarioStep:
    gate: GateKind
    index: int
    target: str
    scenario: ScenarioDefinition
    campaign_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "index": self.index,
            "target": self.target,
            "scenario": self.scenario.name,
            "fault": self.scenario.fault,
            "action": self.scenario.action,
            "expected_outcome": self.scenario.expected_outcome,
            "campaign_hash": self.campaign_hash,
        }


QualificationStep = ScheduleStep | ScenarioStep


@dataclass(frozen=True)
class EvidenceEvent:
    sequence: int
    event_type: str
    payload: Mapping[str, Any]
    previous_hash: str
    event_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "payload": _json_ready(self.payload),
            "previous_hash": self.previous_hash,
            "event_hash": self.event_hash,
        }


class JsonlEvidenceRecorder:
    def __init__(self) -> None:
        self._events: list[EvidenceEvent] = []
        self._tail_hash = GENESIS_HASH

    @property
    def events(self) -> tuple[EvidenceEvent, ...]:
        return tuple(self._events)

    @property
    def tail_hash(self) -> str:
        return self._tail_hash

    def append(self, event_type: str, payload: Mapping[str, Any]) -> EvidenceEvent:
        clean_payload = _json_ready(payload)
        body = {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "sequence": len(self._events) + 1,
            "event_type": event_type,
            "payload": clean_payload,
            "previous_hash": self._tail_hash,
        }
        event_hash = stable_hash(body)
        event = EvidenceEvent(
            sequence=body["sequence"],
            event_type=event_type,
            payload=clean_payload,
            previous_hash=self._tail_hash,
            event_hash=event_hash,
        )
        self._events.append(event)
        self._tail_hash = event_hash
        return event

    def to_jsonl(self) -> str:
        return "".join(_canonical_json(event.to_dict()) + "\n" for event in self._events)

    def write_jsonl(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_jsonl(), encoding="utf-8")


def stable_hash(value: Any) -> str:
    encoded = json.dumps(_json_ready(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def load_reviewed_manifest(path: Path) -> ReviewedManifest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_json_object)
    except json.JSONDecodeError as exc:
        raise P174LiveHarnessError(f"manifest_json_invalid:{exc.msg}") from exc
    if not isinstance(raw, dict):
        raise P174LiveHarnessError("manifest_object_required")
    return parse_reviewed_manifest(raw)


def parse_reviewed_manifest(raw: Mapping[str, Any]) -> ReviewedManifest:
    extra = sorted(set(raw) - _MANIFEST_FIELDS)
    if extra:
        raise P174LiveHarnessError(f"manifest_unreviewed_fields:{','.join(extra)}")
    if raw.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise P174LiveHarnessError("manifest_schema_invalid")
    if raw.get("reviewed") is not True:
        raise P174LiveHarnessError("manifest_review_required")
    manifest_id = _required_id(raw, "manifest_id")
    reviewed_by = _required_id(raw, "reviewed_by")
    reviewed_at = _required_text(raw, "reviewed_at")
    lab_id = _required_id(raw, "lab_id")
    seed = _required_seed(raw)
    observer_contract_hash = _required_sha(raw, "observer_contract_hash")
    action_contract_hash = _required_sha(raw, "action_contract_hash")
    allowed_targets = _required_id_tuple(raw, "allowed_targets")
    allowed_actions = _required_id_tuple(raw, "allowed_actions")
    _reject_forbidden_text(raw)
    return ReviewedManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        manifest_id=manifest_id,
        manifest_hash=stable_hash(raw),
        reviewed=True,
        reviewed_by=reviewed_by,
        reviewed_at=reviewed_at,
        lab_id=lab_id,
        seed=seed,
        observer_contract_hash=observer_contract_hash,
        action_contract_hash=action_contract_hash,
        allowed_targets=allowed_targets,
        allowed_actions=allowed_actions,
    )


def build_seeded_schedule(manifest: ReviewedManifest) -> tuple[QualificationStep, ...]:
    steps: list[ScheduleStep] = []
    for index in range(1, HEALTHY_WINDOW_GATE + 1):
        target = _seeded_pick(manifest.allowed_targets, manifest.seed, index, salt="healthy")
        action = _seeded_pick(manifest.allowed_actions, manifest.seed, index, salt="healthy")
        schedule_hash = stable_hash(
            {
                "manifest_hash": manifest.manifest_hash,
                "seed": manifest.seed,
                "gate": "healthy_window",
                "index": index,
                "target": target,
                "action": action,
            }
        )
        steps.append(ScheduleStep(gate="healthy_window", index=index, target=target, action=action, schedule_hash=schedule_hash))
    return (*steps, *build_seeded_campaign(manifest))


def build_seeded_campaign(manifest: ReviewedManifest, *, limit: int | None = None) -> tuple[ScenarioStep, ...]:
    scenarios: list[ScenarioDefinition] = []
    for name, count in CAMPAIGN_DISTRIBUTION.items():
        definition = _scenario_definition(name)
        scenarios.extend(definition for _ in range(count))
    scenarios.sort(key=lambda scenario: stable_hash({"seed": manifest.seed, "manifest_hash": manifest.manifest_hash, **scenario.to_dict()}))
    if limit is not None:
        scenarios = scenarios[:limit]
    steps: list[ScenarioStep] = []
    for index, scenario in enumerate(scenarios, start=1):
        target = _seeded_pick(manifest.allowed_targets, manifest.seed, index, salt=scenario.name)
        campaign_hash = stable_hash(
            {
                "manifest_hash": manifest.manifest_hash,
                "seed": manifest.seed,
                "gate": "scenario_campaign",
                "index": index,
                "target": target,
                **scenario.to_dict(),
            }
        )
        steps.append(ScenarioStep(gate="scenario_campaign", index=index, target=target, scenario=scenario, campaign_hash=campaign_hash))
    return tuple(steps)


def run_qualification(
    manifest: ReviewedManifest,
    observer: ObserverClient,
    action: ActionClient,
    *,
    recorder: JsonlEvidenceRecorder | None = None,
    max_scenarios: int | None = None,
    diagnostic_campaign_only: bool = False,
) -> dict[str, Any]:
    evidence = recorder or JsonlEvidenceRecorder()
    campaign = build_seeded_campaign(manifest, limit=max_scenarios)
    schedule = campaign if diagnostic_campaign_only else (*build_seeded_schedule(manifest)[:HEALTHY_WINDOW_GATE], *campaign)
    evidence.append(
        "manifest",
        {
            "manifest_id": manifest.manifest_id,
            "manifest_hash": manifest.manifest_hash,
            "lab_id": manifest.lab_id,
            "seed": manifest.seed,
            "schedule_hash": stable_hash([step.to_dict() for step in schedule]),
            "campaign_distribution": CAMPAIGN_DISTRIBUTION,
        },
    )

    healthy_consecutive = 0
    successful_scenarios = 0
    failures: list[dict[str, Any]] = []
    coverage: Counter[str] = Counter()
    seen_window_ids: set[str] = set()
    previous_window_timestamp: datetime | None = None
    previous_window_sequence: int | None = None

    for step in schedule:
        try:
            if step.gate == "healthy_window":
                assert isinstance(step, ScheduleStep)
                observed = _bounded_payload(observer.observe_health_window(step))
                window_id, window_timestamp, window_sequence, parsed_timestamp = _healthy_window_identity(
                    observed,
                    seen_window_ids=seen_window_ids,
                    previous_timestamp=previous_window_timestamp,
                    previous_sequence=previous_window_sequence,
                )
                passed = observed.get("healthy") is True
                if passed:
                    healthy_consecutive += 1
                    seen_window_ids.add(window_id)
                    previous_window_timestamp = parsed_timestamp
                    previous_window_sequence = window_sequence
                else:
                    failures.append(_failure("healthy_window_not_healthy", step, observed))
                evidence.append(
                    "healthy_window",
                    {
                        "step": step.to_dict(),
                        "passed": passed,
                        "window_id": window_id,
                        "timestamp": window_timestamp,
                        "sequence": window_sequence,
                        "observation_hash": stable_hash(observed),
                    },
                )
                if not passed:
                    break
                continue

            if not diagnostic_campaign_only and healthy_consecutive != HEALTHY_WINDOW_GATE:
                failures.append(_failure("healthy_gate_incomplete", step, {"healthy_consecutive": healthy_consecutive}))
                break
            assert isinstance(step, ScenarioStep)
            baseline = _bounded_payload(observer.observe_scenario(step))
            baseline_ready = baseline.get("ready") is True
            stabilization_attempts = _baseline_stabilization_attempts(baseline)
            baseline_observation_hash = stable_hash(baseline)
            if not baseline_ready:
                failures.append(_failure("scenario_baseline_not_ready", step, baseline))
                evidence.append(
                    "scenario_campaign",
                    {
                        "step": step.to_dict(),
                        "passed": False,
                        "baseline_ready": False,
                        "stabilization_attempts": stabilization_attempts,
                        "baseline_hash": _state_hash(baseline),
                        "baseline_observation_hash": baseline_observation_hash,
                        "mutation_attempted": False,
                        "checks": {"baseline_ready": False},
                        "coverage": dict(sorted(coverage.items())),
                    },
                )
                break
            fault_result = _bounded_payload(action.inject_fault(step, baseline))
            try:
                post_result = _bounded_payload(action.run_scenario(step, baseline, fault_result))
            except Exception as action_exc:
                action_error = {"error_type": type(action_exc).__name__, "error": str(action_exc)}
                cleanup_probe = {"status": "action_exception", **action_error}
                exception_evidence: dict[str, Any] = {
                    "step": step.to_dict(),
                    "mutation_attempted": True,
                    "cleanup_attempted": True,
                    **action_error,
                }
                try:
                    cleanup_result = _bounded_payload(action.cleanup_scenario(step, baseline, cleanup_probe))
                    cleanup_proven = _protected_state(_state(cleanup_result, "cleanup")) == _protected_state(
                        _fault_baseline_state(fault_result)
                    )
                    exception_evidence["cleanup_proven"] = cleanup_proven
                    exception_evidence["cleanup_hash"] = _state_hash(cleanup_result)
                except Exception as cleanup_exc:
                    exception_evidence["cleanup_proven"] = False
                    exception_evidence["cleanup_error_type"] = type(cleanup_exc).__name__
                    exception_evidence["cleanup_error"] = str(cleanup_exc)
                try:
                    exception_evidence["fault_hash"] = _state_hash(fault_result)
                except Exception as fault_hash_exc:
                    exception_evidence["fault_hash_error_type"] = type(fault_hash_exc).__name__
                    exception_evidence["fault_hash_error"] = str(fault_hash_exc)
                failures.append(_failure("client_exception", step, exception_evidence))
                evidence.append("exception", exception_evidence)
                break
            cleanup_result = _bounded_payload(action.cleanup_scenario(step, baseline, post_result))
            verdict = _scenario_verdict(step, baseline, fault_result, post_result, cleanup_result)
            passed = verdict["passed"] is True
            if passed:
                successful_scenarios += 1
                _count_coverage(coverage, step)
            else:
                failures.append(_failure("scenario_claim_not_proven", step, verdict))
            evidence.append(
                "scenario_campaign",
                {
                    "step": step.to_dict(),
                    "passed": passed,
                    "baseline_ready": baseline_ready,
                    "stabilization_attempts": stabilization_attempts,
                    "baseline_hash": _fault_baseline_hash(fault_result),
                    "baseline_observation_hash": baseline_observation_hash,
                    "mutation_attempted": True,
                    "fault_hash": _state_hash(fault_result),
                    "post_hash": _state_hash(post_result),
                    "cleanup_hash": _state_hash(cleanup_result),
                    "checks": verdict["checks"],
                    "post_status": verdict["post_status"],
                    "post_failure_reason": verdict["post_failure_reason"],
                    "post_failure_detail": verdict["post_failure_detail"],
                    "post_state_sequence": verdict["post_state_sequence"],
                    "rollback_closure_claimed": verdict["rollback_closure_claimed"],
                    "delta": verdict["delta"],
                    "coverage": dict(sorted(coverage.items())),
                },
            )
            if not passed:
                break
        except Exception as exc:
            failures.append(_failure("client_exception", step, {"error_type": type(exc).__name__, "error": str(exc)}))
            evidence.append("exception", {"step": step.to_dict(), "error_type": type(exc).__name__, "error": str(exc)})
            break

    scenario_gate_passed = successful_scenarios == SCENARIO_CAMPAIGN_GATE
    qualified = not diagnostic_campaign_only and healthy_consecutive == HEALTHY_WINDOW_GATE and scenario_gate_passed and not failures
    status = "diagnostic_complete" if diagnostic_campaign_only and scenario_gate_passed and not failures else "qualified" if qualified else "blocked"
    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "status": status,
        "qualified": qualified,
        "fail_closed": not qualified,
        "diagnostic_campaign_only": diagnostic_campaign_only,
        "manifest_hash": manifest.manifest_hash,
        "seed": manifest.seed,
        "gates": {
            "healthy_window": {"required_consecutive": HEALTHY_WINDOW_GATE, "observed_consecutive": healthy_consecutive, "passed": healthy_consecutive == HEALTHY_WINDOW_GATE},
            "scenario_campaign": {
                "required_exact": SCENARIO_CAMPAIGN_GATE,
                "observed_successful": successful_scenarios,
                "passed": scenario_gate_passed,
            },
        },
        "campaign": {
            "required_exact": SCENARIO_CAMPAIGN_GATE,
            "diagnostic_limit": max_scenarios,
            "distribution": CAMPAIGN_DISTRIBUTION,
            "campaign_hash": stable_hash([step.to_dict() for step in build_seeded_campaign(manifest)]),
        },
        "coverage_counters": dict(sorted(coverage.items())),
        "failure_count": len(failures),
        "failures": failures,
        "evidence": {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "event_count": len(evidence.events),
            "genesis_hash": GENESIS_HASH,
            "tail_hash": evidence.tail_hash,
            "jsonl_hash": stable_hash(evidence.to_jsonl()),
        },
    }
    return summary


def verify_evidence_jsonl(text: str) -> dict[str, Any]:
    previous = GENESIS_HASH
    count = 0
    for line in text.splitlines():
        count += 1
        event = json.loads(line, object_pairs_hook=_strict_json_object)
        claimed = event.get("event_hash")
        body = {key: event[key] for key in ("schema_version", "sequence", "event_type", "payload", "previous_hash")}
        if event.get("previous_hash") != previous:
            raise P174LiveHarnessError(f"evidence_chain_broken:{count}")
        if stable_hash(body) != claimed:
            raise P174LiveHarnessError(f"evidence_hash_mismatch:{count}")
        previous = str(claimed)
    return {"schema_version": EVIDENCE_SCHEMA_VERSION, "event_count": count, "tail_hash": previous, "jsonl_hash": stable_hash(text)}


def _scenario_verdict(
    step: ScenarioStep,
    baseline: Mapping[str, Any],
    fault_result: Mapping[str, Any],
    post_result: Mapping[str, Any],
    cleanup_result: Mapping[str, Any],
) -> dict[str, Any]:
    observed_baseline_state = _state(baseline, "observed_baseline")
    baseline_state = _fault_baseline_state(fault_result)
    fault_state = _state(fault_result, "fault")
    post_state = _state(post_result, "post")
    cleanup_state = _state(cleanup_result, "cleanup")
    hashes_match = (
        _state_hash(baseline) == stable_hash(observed_baseline_state)
        and _fault_baseline_hash(fault_result) == stable_hash(baseline_state)
        and _state_hash(fault_result) == stable_hash(fault_state)
        and _state_hash(post_result) == stable_hash(post_state)
        and _state_hash(cleanup_result) == stable_hash(cleanup_state)
    )
    if not hashes_match:
        return {"passed": False, "reason": "state_hash_mismatch", "delta": {}}
    delta = _state_delta(baseline_state, fault_state, post_state, cleanup_state)
    fault_ok = _fault_delta_proven(step.scenario.fault, baseline_state, fault_state)
    expected_ok = _expected_delta_proven(step.scenario.expected_outcome, step.scenario.action, fault_state, post_state, post_result)
    cleanup_ok = _protected_state(cleanup_state) == _protected_state(baseline_state)
    checks = {
        "baseline_ready": baseline.get("ready") is True,
        "fault_accepted": fault_result.get("accepted") is True,
        "fault_delta_proven": fault_ok,
        "expected_delta_proven": expected_ok,
        "cleanup_proven": cleanup_ok,
    }
    return {
        "passed": all(checks.values()),
        "reason": "ok" if all(checks.values()) else "claim_not_proven",
        "checks": checks,
        "post_status": post_result.get("status"),
        "post_failure_reason": post_result.get("failure_reason"),
        "post_failure_detail": post_result.get("failure_detail"),
        "post_state_sequence": post_result.get("state_sequence"),
        "rollback_closure_claimed": post_result.get("rollback_closure_claimed") is True,
        "delta": delta,
    }


def _baseline_stabilization_attempts(baseline: Mapping[str, Any]) -> int:
    value = baseline.get("stabilization_attempts")
    if not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > MAX_BASELINE_STABILIZATION_ATTEMPTS:
        raise P174LiveHarnessError("baseline_stabilization_attempts_invalid")
    return value


def _fault_delta_proven(fault: str, baseline: Mapping[str, Any], fault_state: Mapping[str, Any]) -> bool:
    if fault == "queue_backlog":
        return _num(fault_state, "queue_depth") > _num(baseline, "queue_depth")
    if fault == "canary_regression":
        return fault_state.get("canary_version") == "regressed" and _num(fault_state, "error_rate") > _num(baseline, "error_rate")
    if fault == "worker_pause":
        return fault_state.get("worker_paused") is True or str(fault_state.get("worker_paused_until", "")) > str(baseline.get("worker_paused_until", ""))
    return False


def _expected_delta_proven(expected: ExpectedOutcome, action_name: str, fault_state: Mapping[str, Any], post_state: Mapping[str, Any], result: Mapping[str, Any]) -> bool:
    status = result.get("status")
    if expected == "applied" and action_name == "restart_worker":
        queue_recovered = _num(post_state, "queue_depth") < _num(fault_state, "queue_depth")
        worker_restarted = _num(post_state, "worker_restart_generation") > _num(fault_state, "worker_restart_generation")
        return status == "applied" and queue_recovered and worker_restarted
    if expected == "applied" and action_name == "rollback_canary":
        return status == "applied" and post_state.get("canary_version") == "stable" and _num(post_state, "error_rate") < _num(fault_state, "error_rate")
    if expected == "rolled_back":
        return action_name == "tune_pool" and status == "rolled_back" and result.get("rollback_closure_claimed") is True and _protected_state(post_state) == _protected_state(fault_state)
    if expected in {"rejected", "blocked_no_mutation"}:
        wanted = "rejected" if expected == "rejected" else "blocked"
        return status == wanted and _protected_state(post_state) == _protected_state(fault_state)
    if expected == "failed_closed":
        return action_name == "restart_worker" and status == "failed_closed" and result.get("irreversible_action") is True and result.get("rollback_closure_claimed") is not True
    return False


def _state_delta(baseline: Mapping[str, Any], fault: Mapping[str, Any], post: Mapping[str, Any], cleanup: Mapping[str, Any]) -> dict[str, Any]:
    keys = sorted(set(baseline) | set(fault) | set(post) | set(cleanup))
    return {
        key: {
            "baseline": baseline.get(key),
            "fault": fault.get(key),
            "post": post.get(key),
            "cleanup": cleanup.get(key),
        }
        for key in keys
        if len({json.dumps(_json_ready(value), sort_keys=True) for value in (baseline.get(key), fault.get(key), post.get(key), cleanup.get(key))}) > 1
    }


def _state(payload: Mapping[str, Any], label: str) -> dict[str, Any]:
    state = payload.get("state")
    if not isinstance(state, Mapping):
        raise P174LiveHarnessError(f"{label}_state_missing")
    return _json_ready(state)


def _state_hash(payload: Mapping[str, Any]) -> str:
    value = payload.get("state_hash")
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise P174LiveHarnessError("state_hash_missing_or_invalid")
    state = payload.get("state")
    if value != stable_hash(state):
        raise P174LiveHarnessError("state_hash_mismatch")
    return value


def _fault_baseline_state(fault_result: Mapping[str, Any]) -> dict[str, Any]:
    state = fault_result.get("baseline_state")
    if not isinstance(state, Mapping):
        raise P174LiveHarnessError("fault_baseline_state_missing")
    return _json_ready(state)


def _fault_baseline_hash(fault_result: Mapping[str, Any]) -> str:
    value = fault_result.get("baseline_state_hash")
    if not isinstance(value, str):
        raise P174LiveHarnessError("fault_baseline_hash_missing")
    return value


def _protected_state(state: Mapping[str, Any]) -> dict[str, Any]:
    missing = [key for key in _PROTECTED_STATE_FIELDS if key not in state]
    if missing:
        raise P174LiveHarnessError(f"protected_state_missing:{','.join(missing)}")
    return {key: state[key] for key in _PROTECTED_STATE_FIELDS}


def _num(value: Mapping[str, Any], key: str) -> float:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int | float) or not math.isfinite(float(item)):
        raise P174LiveHarnessError(f"numeric_state_required:{key}")
    return float(item)


def _scenario_definition(name: str) -> ScenarioDefinition:
    if name == "restart_recovery":
        return ScenarioDefinition("restart_recovery", "queue_backlog", "restart_worker", "applied")
    if name == "canary_rollback":
        return ScenarioDefinition("canary_rollback", "canary_regression", "rollback_canary", "applied")
    if name == "rejection":
        return ScenarioDefinition("rejection", "queue_backlog", "unsupported_action", "rejected")
    if name == "rollback_required":
        return ScenarioDefinition("rollback_required", "worker_pause", "tune_pool", "rolled_back")
    if name == "safety_boundary":
        return ScenarioDefinition("safety_boundary", "canary_regression", "tune_pool", "blocked_no_mutation")
    raise P174LiveHarnessError(f"unknown_scenario:{name}")


def _count_coverage(counter: Counter[str], step: ScenarioStep) -> None:
    counter[step.scenario.name] += 1
    counter[f"fault:{step.scenario.fault}"] += 1
    counter[f"action:{step.scenario.action}"] += 1
    counter[f"expected:{step.scenario.expected_outcome}"] += 1


def _seeded_pick(values: Sequence[str], seed: int, index: int, *, salt: str) -> str:
    selected = stable_hash({"seed": seed, "index": index, "salt": salt})
    offset = int(selected.removeprefix("sha256:")[:8], 16) % len(values)
    return values[offset]


def _bounded_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    clean = _json_ready(payload)
    if not isinstance(clean, dict):
        raise P174LiveHarnessError("client_payload_object_required")
    _reject_forbidden_text(clean)
    return clean


def _healthy_window_identity(
    observed: Mapping[str, Any],
    *,
    seen_window_ids: set[str],
    previous_timestamp: datetime | None,
    previous_sequence: int | None,
) -> tuple[str, str, int, datetime]:
    window_id = observed.get("window_id")
    if not isinstance(window_id, str) or not _ID_RE.fullmatch(window_id):
        raise P174LiveHarnessError("healthy_window_id_invalid")
    if window_id in seen_window_ids:
        raise P174LiveHarnessError("healthy_window_id_duplicate")

    timestamp = observed.get("timestamp")
    if not isinstance(timestamp, str):
        raise P174LiveHarnessError("healthy_window_timestamp_invalid")
    try:
        parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise P174LiveHarnessError("healthy_window_timestamp_invalid") from exc
    if parsed_timestamp.tzinfo is None or parsed_timestamp.utcoffset() is None:
        raise P174LiveHarnessError("healthy_window_timestamp_invalid")
    if previous_timestamp is not None and (parsed_timestamp - previous_timestamp).total_seconds() < MIN_HEALTHY_WINDOW_DELTA_SECONDS:
        raise P174LiveHarnessError("healthy_window_timestamp_too_rapid")

    sequence = observed.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise P174LiveHarnessError("healthy_window_sequence_invalid")
    if previous_sequence is not None and sequence <= previous_sequence:
        raise P174LiveHarnessError("healthy_window_sequence_not_increasing")
    return window_id, timestamp, sequence, parsed_timestamp


def _failure(reason: str, step: QualificationStep, details: Mapping[str, Any]) -> dict[str, Any]:
    return {"reason": reason, "step": step.to_dict(), "details_hash": stable_hash(details)}


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise P174LiveHarnessError(f"duplicate_json_key:{key}")
        value[key] = item
    return value


def _required_id(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise P174LiveHarnessError(f"{key}_invalid")
    return value


def _required_text(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value or len(value) > 128:
        raise P174LiveHarnessError(f"{key}_invalid")
    return value


def _required_seed(raw: Mapping[str, Any]) -> int:
    value = raw.get("seed")
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 2**32 - 1:
        raise P174LiveHarnessError("seed_invalid")
    return value


def _required_sha(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise P174LiveHarnessError(f"{key}_invalid")
    return value


def _required_id_tuple(raw: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise P174LiveHarnessError(f"{key}_invalid")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not _ID_RE.fullmatch(item):
            raise P174LiveHarnessError(f"{key}_item_invalid")
        if item in items:
            raise P174LiveHarnessError(f"{key}_duplicate")
        items.append(item)
    return tuple(items)


def _reject_forbidden_text(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or _FORBIDDEN_TEXT_RE.search(key):
                raise P174LiveHarnessError("forbidden_manifest_or_payload_text")
            _reject_forbidden_text(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _reject_forbidden_text(item)
    elif isinstance(value, str) and _FORBIDDEN_TEXT_RE.search(value):
        raise P174LiveHarnessError("forbidden_manifest_or_payload_text")


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_ready(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _canonical_json(value: Any) -> str:
    return json.dumps(_json_ready(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
