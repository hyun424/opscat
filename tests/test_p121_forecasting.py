from __future__ import annotations

import pytest

from app.services.p121_forecasting import (
    P121EvidenceError,
    build_evidence_receipt,
    build_prevention_decision,
    evidence_gaps,
)
from app.services.p121_signals import zero_authority_counters

HASH = "sha256:" + "b" * 64


def _evidence(**patch: object) -> dict[str, object]:
    base: dict[str, object] = {
        "evidence_id": "ev-1",
        "source_ref": "fixture://checkout/latency-window",
        "source_kind": "local_fixture",
        "taxonomy_version": "p121.taxonomy.v1",
        "artifact_hash": HASH,
        "observed_at": "2026-07-12T00:05:00Z",
        "cutoff_at": "2026-07-12T00:10:00Z",
        "collected_at": "2026-07-12T00:06:00Z",
        "staleness_seconds": 60,
        "max_staleness_seconds": 300,
        "contradiction_status": "none",
        "post_intervention": False,
        "denominator_visible": True,
        "authority_counters": zero_authority_counters(),
    }
    return {**base, **patch}


def test_evidence_receipt_is_local_read_only_hash_bound_and_visible() -> None:
    receipt = build_evidence_receipt(_evidence())

    assert receipt["evidence_hash"].startswith("sha256:")
    assert receipt["denominator_visible"] is True
    assert receipt["authority_counters"] == zero_authority_counters()


@pytest.mark.parametrize(
    ("patch", "expected"),
    [
        ({"source_kind": "live_connector"}, "nonlocal_evidence"),
        ({"artifact_hash": "missing"}, "invalid_artifact_hash"),
        ({"observed_at": "2026-07-12T00:11:00Z"}, "post_cutoff_evidence"),
        ({"staleness_seconds": 600}, "stale_evidence"),
        ({"contradiction_status": "contradicts_ev_9"}, "contradictory_evidence"),
        ({"post_intervention": True}, "post_intervention_evidence"),
        ({"authority_counters": {**zero_authority_counters(), "live_connector_call_count": 1}}, "live_connector_call_count_nonzero"),
    ],
)
def test_evidence_red_cases_fail_closed(patch: dict[str, object], expected: str) -> None:
    with pytest.raises(P121EvidenceError, match=expected):
        build_evidence_receipt(_evidence(**patch))


def test_preventive_decision_requires_all_evidence_before_action() -> None:
    receipt = build_evidence_receipt(_evidence())
    decision = build_prevention_decision(
        {"decision_id": "dec-1", "forecast_id": "fc-1", "route": "prevent_l1_recommend", "required_evidence_ids": ["ev-1"], "authority_counters": zero_authority_counters()},
        [receipt],
    )

    assert decision["route"] == "prevent_l1_recommend"
    assert decision["release_blocker"] is False
    assert decision["decision_hash"].startswith("sha256:")


def test_missing_evidence_routes_to_investigate_more() -> None:
    decision = build_prevention_decision(
        {"decision_id": "dec-2", "forecast_id": "fc-1", "route": "prevent_l2_dry_run", "required_evidence_ids": ["ev-1"], "authority_counters": zero_authority_counters()},
        [],
    )

    assert decision["route"] == "investigate_more"
    assert decision["reason"] == "missing_required_evidence"


def test_evidence_bypass_attempt_fails_closed_as_release_blocker() -> None:
    decision = build_prevention_decision(
        {"decision_id": "dec-3", "forecast_id": "fc-1", "route": "prevent_l3_local_sandbox", "required_evidence_ids": [], "authority_counters": zero_authority_counters()},
        [],
    )

    assert decision["route"] == "abstain_fail_closed"
    assert decision["release_blocker"] is True
    assert decision["reason"] == "evidence_bypass_intervention"


def test_evidence_gaps_preserve_invalid_evidence_reasons() -> None:
    gaps = evidence_gaps(["ev-1", "ev-2"], [_evidence(staleness_seconds=999)])

    assert gaps == ["missing_required_evidence", "stale_evidence"]
