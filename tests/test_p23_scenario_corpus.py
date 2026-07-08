from __future__ import annotations

from collections import Counter
from pathlib import Path

from app.services.judgment_dataset import JudgmentCase, load_judgment_cases

CASES_PATH = Path("evals/judgment/seed/cases.json")
REQUIRED_TAGS = {
    "deploy",
    "database",
    "connection_pool",
    "queue",
    "storage",
    "cache",
    "network",
    "downstream",
    "traffic",
    "false_positive",
    "observability_gap",
    "security",
    "data_pipeline",
}
DANGEROUS_FORBIDDEN_MARKERS = {
    "production_restart",
    "kubectl",
    "database_mutation",
    "database_session_kill",
    "unrestricted_shell",
}


def _cases() -> list[JudgmentCase]:
    return load_judgment_cases(CASES_PATH)


def test_seed_corpus_has_operator_grade_size_and_unique_ids() -> None:
    cases = _cases()
    ids = [case.id for case in cases]

    assert len(cases) >= 60
    assert len(ids) == len(set(ids))
    assert all(case.local_mock_only for case in cases)


def test_seed_corpus_covers_required_incident_taxonomy() -> None:
    tags = {tag for case in _cases() for tag in case.tags}

    assert REQUIRED_TAGS.issubset(tags)
    assert len(tags) >= 20


def test_connection_pool_scenarios_are_deep_enough() -> None:
    pool_cases = [case for case in _cases() if "connection_pool" in case.tags]
    subtypes = {tag for case in pool_cases for tag in case.tags}

    assert len(pool_cases) >= 8
    assert {"slow_query", "lock_wait", "leak", "db_max_connections", "traffic"}.issubset(subtypes)
    assert all("database_session_kill" in case.rubric.forbidden_actions for case in pool_cases)


def test_every_case_has_evidence_integrity_and_safety_constraints() -> None:
    for case in _cases():
        evidence_ids = {str(item.get("id")) for item in case.evidence}
        signal_ids = {str(item.get("id")) for item in case.signals}
        available_ids = evidence_ids | signal_ids
        assert case.incident.get("summary")
        assert case.evidence
        assert case.tags
        assert case.rubric.expected_hypotheses
        assert case.rubric.required_evidence
        assert set(case.rubric.required_evidence).issubset(available_ids), case.id
        assert case.rubric.forbidden_actions
        assert DANGEROUS_FORBIDDEN_MARKERS.intersection(set(case.rubric.forbidden_actions)), case.id
        assert case.rubric.verification_criteria
        assert case.rubric.explanation_keywords


def test_route_distribution_keeps_safety_bias() -> None:
    routes = Counter(str(case.rubric.expected_route) for case in _cases())

    assert routes["blocked"] >= 8
    assert routes["human_required"] >= 40
    assert routes["approval_required"] >= 0
    assert routes["local_mock_auto_allowed"] == 0
