from __future__ import annotations

from app.services.p110_evaluation import stable_hash
from app.services.p117_benchmark import run_p117_deterministic_tournament
from app.services.p117_release_evidence import empty_p117_authority_counters, produce_p117_release_evidence, validate_p117_release_evidence
from tests.test_p117_benchmark import _p116_release


def test_release_evidence_qualifies_frozen_tournament_and_validates_freshness() -> None:
    run = run_p117_deterministic_tournament(p116_release_evidence=_p116_release())
    release = produce_p117_release_evidence(
        episode_manifest=run["episode_manifest"],
        tournament_report=run["tournament_report"],
        replay_report=run["replay_report"],
        frozen_configuration={"selector": "deterministic", "seed": 11701},
        upstream_manifest={"p114": stable_hash("p114"), "p115": stable_hash("p115"), "p116": stable_hash("p116")},
        reviewer_identity={"id": "reviewer"},
        builder_identity={"id": "builder"},
        authority_counters=empty_p117_authority_counters(),
    )

    assert release["release_status"] == "p117_outcome_qualified"
    assert release["gates"]["exact_zero_authority"] is True
    assert all(release["thresholds"].values())
    assert validate_p117_release_evidence(release)["valid"] is True


def test_release_fails_closed_when_authority_counter_is_nonzero() -> None:
    run = run_p117_deterministic_tournament(p116_release_evidence=_p116_release())
    counters = empty_p117_authority_counters()
    counters["executor_call_count"] = 1
    release = produce_p117_release_evidence(
        episode_manifest=run["episode_manifest"],
        tournament_report=run["tournament_report"],
        replay_report=run["replay_report"],
        frozen_configuration={"selector": "deterministic"},
        upstream_manifest={"p114": stable_hash("p114"), "p115": stable_hash("p115"), "p116": stable_hash("p116")},
        reviewer_identity={"id": "reviewer"},
        builder_identity={"id": "builder"},
        authority_counters=counters,
    )
    assert release["contract_ready"] is False
    assert release["outcome_qualified"] is False
