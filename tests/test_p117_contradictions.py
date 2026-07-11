from __future__ import annotations

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p117_contradictions import (
    CONTRADICTION_KINDS,
    P117ContradictionError,
    build_contradiction_ledger,
    decide_contradiction_fallback,
)


def test_contradiction_ledger_preserves_all_first_class_kinds_and_hashes() -> None:
    ledger = build_contradiction_ledger(
        [
            {
                "kind": "p114_hypothesis_conflict",
                "affected_action_pack_ids": ["pack-a"],
                "affected_evidence_ids": ["ev-a", "ev-b"],
                "severity": 0.45,
                "description": "two sealed hypotheses cite opposite metric direction",
            },
            {
                "kind": "p116_seed_disagreement",
                "affected_action_pack_ids": ["pack-a"],
                "affected_evidence_ids": ["ev-c"],
                "severity": 0.82,
                "description": "paired outcome benefit changes sign across seeds",
            },
        ]
    ).to_dict()

    assert "natural_recovery_ambiguity" in CONTRADICTION_KINDS
    assert [item["kind"] for item in ledger["contradictions"]] == ["p114_hypothesis_conflict", "p116_seed_disagreement"]
    assert ledger["max_severity"] == 0.82
    assert ledger["ledger_hash"] == stable_hash({key: value for key, value in ledger.items() if key != "ledger_hash"})


def test_contradiction_thresholds_force_cited_fallbacks() -> None:
    ledger = build_contradiction_ledger(
        [
            {
                "kind": "contraindication_conflict",
                "affected_action_pack_ids": ["pack-danger"],
                "affected_evidence_ids": ["ev-safety"],
                "severity": 0.9,
                "description": "contraindication is present",
            }
        ]
    )

    decision = decide_contradiction_fallback(ledger).to_dict()

    assert decision["selected_label"] == "abstain"
    assert decision["fallback_reason"] == "contradiction_threshold_exceeded"
    assert decision["contradiction_set_ids"] == [ledger.to_dict()["contradictions"][0]["contradiction_id"]]
    assert decision["changed_decision"] is True


def test_moderate_contradictions_request_more_evidence_without_suppression() -> None:
    ledger = build_contradiction_ledger(
        [
            {
                "kind": "timestamp_conflict",
                "affected_action_pack_ids": ["pack-a"],
                "affected_evidence_ids": ["ev-old", "ev-new"],
                "severity": 0.5,
                "description": "evidence windows disagree",
            }
        ]
    )

    decision = decide_contradiction_fallback(ledger).to_dict()

    assert decision["selected_label"] == "investigate_more"
    assert decision["fallback_reason"] == "contradiction_requires_evidence"
    assert decision["contradiction_suppression_count"] == 0


@pytest.mark.parametrize(
    ("item", "error"),
    [
        ({"kind": "aggregate_confidence", "affected_action_pack_ids": ["pack-a"], "affected_evidence_ids": ["ev-a"], "severity": 0.2, "description": "hidden"}, "unknown_contradiction_kind"),
        ({"kind": "source_conflict", "affected_action_pack_ids": [], "affected_evidence_ids": ["ev-a"], "severity": 0.2, "description": "missing action"}, "missing_affected_action_pack_ids"),
        ({"kind": "source_conflict", "affected_action_pack_ids": ["pack-a"], "affected_evidence_ids": ["ev-a"], "severity": 1.2, "description": "bad severity"}, "invalid_severity"),
    ],
)
def test_contradiction_ledger_fails_closed(item: dict[str, object], error: str) -> None:
    with pytest.raises(P117ContradictionError, match=error):
        build_contradiction_ledger([item])
