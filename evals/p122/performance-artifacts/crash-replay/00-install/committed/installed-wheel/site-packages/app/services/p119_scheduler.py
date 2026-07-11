"""P119 fixture alert dedupe, correlation, and budgeted scheduler."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p119_contract import P119ContractError, P119IncidentEnvelope, build_incident_envelope, exact_zero_authority_counters, reject_authority_boundary
from app.services.p119_ledger import P119LedgerReceipt, P119LedgerStore


class P119SchedulerError(ValueError):
    """Raised when alert scheduling must fail closed."""


@dataclass(frozen=True)
class P119SchedulerDecision:
    outcome: str
    incident_id: str
    reason: str
    receipt: P119LedgerReceipt
    correlated_incident_ids: tuple[str, ...]
    authority_counter_snapshot: Mapping[str, int]


class P119BudgetedScheduler:
    def __init__(self, ledger: P119LedgerStore, *, frozen_manifest_hash: str) -> None:
        self.ledger = ledger
        self.frozen_manifest_hash = frozen_manifest_hash
        self._active_by_fingerprint: dict[str, str] = {}
        self._incident_by_fingerprint: dict[str, P119IncidentEnvelope] = {}
        self._fixture_index: dict[str, set[str]] = {}
        self._terminal_by_fingerprint: set[str] = set()

    def ingest_alert(self, alert: Mapping[str, Any], *, now: int) -> P119SchedulerDecision:
        fingerprint = _required_text(alert, "alert_fingerprint")
        fixture_id = _fixture(alert.get("fixture_id"))
        reject_authority_boundary(alert)
        incident_id = _required_text(alert, "incident_id")
        if alert.get("manifest_hash") != self.frozen_manifest_hash:
            raise P119SchedulerError("stale_frozen_manifest_hash")
        if fingerprint in self._terminal_by_fingerprint and alert.get("recurrence_receipt") is None:
            raise P119SchedulerError("stale_alert_replay")
        existing_id = self._active_by_fingerprint.get(fingerprint)
        if existing_id is not None:
            receipt = self.ledger.register_incident(self._incident_by_fingerprint[fingerprint])
            return P119SchedulerDecision("deduplicated", existing_id, "duplicate_alert_fingerprint", receipt, (), exact_zero_authority_counters())
        correlated = tuple(sorted(self._fixture_index.get(fixture_id, set())))
        incident = build_incident_envelope(
            {
                "incident_id": incident_id,
                "schema_version": "p119.incident_envelope.v1",
                "alert_fingerprint": fingerprint,
                "fixture_id": fixture_id,
                "state": "detected",
                "wal_position": 0,
                "cas_version": 0,
                "idempotency_key": _required_text(alert, "idempotency_key"),
                "budget_snapshot": _budget(alert),
                "timeline_hash": stable_hash({"incident_id": incident_id, "alert_fingerprint": fingerprint, "now": now}),
                "replay_refs": ["replay:alert-fixture"],
                "authority_counter_snapshot": exact_zero_authority_counters(),
            }
        )
        receipt = self.ledger.register_incident(incident)
        self._active_by_fingerprint[fingerprint] = incident_id
        self._incident_by_fingerprint[fingerprint] = incident
        self._fixture_index.setdefault(fixture_id, set()).add(incident_id)
        outcome = "created" if not correlated else "correlated"
        reason = "new_alert" if not correlated else "near_duplicate_fixture_alert"
        return P119SchedulerDecision(outcome, incident_id, reason, receipt, correlated, exact_zero_authority_counters())

    def evaluate_budget(self, incident_id: str, budget_snapshot: Mapping[str, Any]) -> P119SchedulerDecision:
        exhausted = _exhausted_budget_reason(budget_snapshot)
        state = self.ledger.replay(incident_id)
        if exhausted is None:
            receipt = self.ledger.transition(incident_id, "triage_started", expected_cas_version=state.cas_version)
            return P119SchedulerDecision("scheduled", incident_id, "budget_available", receipt, (), exact_zero_authority_counters())
        target_state = "expired" if exhausted in {"incident_wall_clock_budget", "per_state_timeout"} else "escalated"
        receipt = self.ledger.transition(incident_id, target_state, expected_cas_version=state.cas_version, reason=exhausted)
        self._terminal_by_fingerprint.add(state.alert_fingerprint)
        return P119SchedulerDecision(target_state, incident_id, exhausted, receipt, (), exact_zero_authority_counters())


def _exhausted_budget_reason(budget: Mapping[str, Any]) -> str | None:
    budget_keys = (
        "incident_wall_clock_budget",
        "per_state_timeout",
        "evidence_attempts_remaining",
        "approval_wait_remaining",
        "validation_window_remaining",
        "rollback_window_remaining",
        "retry_remaining",
        "wal_entries_remaining",
    )
    for key in budget_keys:
        value = budget.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value <= 0:
            return key
    return None


def _budget(alert: Mapping[str, Any]) -> Mapping[str, Any]:
    value = alert.get("budget_snapshot")
    if not isinstance(value, Mapping) or not value:
        raise P119SchedulerError("missing_budget_snapshot")
    return value


def _required_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise P119SchedulerError(f"missing_{key}")
    return value.strip()


def _fixture(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith(("local:fixture:", "mock:fixture:", "sandbox:fixture:")):
        raise P119SchedulerError("invalid_fixture_id")
    try:
        reject_authority_boundary({"fixture_id": value})
    except P119ContractError as exc:
        raise P119SchedulerError(str(exc)) from exc
    return value
