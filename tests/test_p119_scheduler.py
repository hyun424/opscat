from __future__ import annotations

import pytest

from app.services.p119_ledger import P119LedgerStore
from app.services.p119_scheduler import P119BudgetedScheduler, P119SchedulerError


def test_scheduler_deduplicates_identical_alerts_and_correlates_fixture_neighbors(tmp_path) -> None:  # type: ignore[no-untyped-def]
    scheduler = P119BudgetedScheduler(P119LedgerStore(tmp_path / "p119.jsonl"), frozen_manifest_hash=_hash("1"))

    first = scheduler.ingest_alert(_alert("inc-1", "fp-1"), now=1)
    duplicate = scheduler.ingest_alert(_alert("inc-ignored", "fp-1"), now=2)
    correlated = scheduler.ingest_alert(_alert("inc-2", "fp-2"), now=3)

    assert first.outcome == "created"
    assert duplicate.outcome == "deduplicated"
    assert duplicate.incident_id == "inc-1"
    assert correlated.outcome == "correlated"
    assert correlated.correlated_incident_ids == ("inc-1",)


def test_scheduler_routes_budget_exhaustion_to_terminal_without_forced_action(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ledger = P119LedgerStore(tmp_path / "p119.jsonl")
    scheduler = P119BudgetedScheduler(ledger, frozen_manifest_hash=_hash("1"))
    scheduler.ingest_alert(_alert("inc-1", "fp-1"), now=1)

    decision = scheduler.evaluate_budget("inc-1", {"incident_wall_clock_budget": 0, "evidence_attempts_remaining": 1})

    assert decision.outcome == "expired"
    assert decision.receipt.state == "expired"
    assert ledger.replay("inc-1").state == "expired"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda alert: alert.__setitem__("manifest_hash", _hash("2")), "stale_frozen_manifest_hash"),
        (lambda alert: alert.__setitem__("fixture_id", "production:checkout"), "invalid_fixture_id"),
        (lambda alert: alert.__setitem__("production_target", "prod"), "forbidden_authority"),
    ],
)
def test_scheduler_red_alert_inputs_fail_closed(tmp_path, mutate: object, message: str) -> None:  # type: ignore[no-untyped-def]
    scheduler = P119BudgetedScheduler(P119LedgerStore(tmp_path / "p119.jsonl"), frozen_manifest_hash=_hash("1"))
    alert = _alert("inc-1", "fp-1")
    mutate(alert)  # type: ignore[operator]

    with pytest.raises((P119SchedulerError, ValueError), match=message):
        scheduler.ingest_alert(alert, now=1)


def _alert(incident_id: str, fingerprint: str) -> dict[str, object]:
    return {
        "incident_id": incident_id,
        "alert_fingerprint": fingerprint,
        "fixture_id": "local:fixture:checkout-api",
        "idempotency_key": f"idem:{incident_id}:{fingerprint}",
        "manifest_hash": _hash("1"),
        "budget_snapshot": {"incident_wall_clock_budget": 30, "evidence_attempts_remaining": 2, "retry_remaining": 1},
    }


def _hash(suffix: str) -> str:
    return "sha256:" + suffix * 64
