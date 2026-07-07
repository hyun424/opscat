from __future__ import annotations

import json
from pathlib import Path

from app.services.judgment_corpus import (
    audit_judgment_corpus,
    build_seed_corpus,
    corpus_archetypes,
    render_corpus_markdown,
    sample_corpus_cases,
    write_corpus_pack,
)
from app.services.judgment_dataset import load_judgment_cases


def test_p11_archetype_catalog_covers_core_sre_failure_modes() -> None:
    archetypes = corpus_archetypes()
    keys = {item.key for item in archetypes}

    assert len(archetypes) >= 17
    for required in {
        "deploy_regression",
        "db_saturation",
        "memory_leak",
        "cpu_spike",
        "queue_backlog",
        "downstream_timeout",
        "rate_limit",
        "disk_full",
        "cert_expiry",
        "dns_failure",
        "crashloop",
        "bad_config",
        "noisy_false_positive",
        "no_data",
        "partial_outage",
        "cascading_failure",
        "prompt_injection",
    }:
        assert required in keys
    assert all(item.expected_hypotheses for item in archetypes)
    assert all(item.evidence_templates for item in archetypes)


def test_p11_seed_corpus_has_broad_local_mock_coverage_and_stable_ids(tmp_path: Path) -> None:
    cases = build_seed_corpus()
    audit = audit_judgment_corpus(cases)
    payload = audit.to_dict()

    assert len(cases) >= 50
    assert len({case.id for case in cases}) == len(cases)
    assert payload["passed"] is True
    assert payload["total_cases"] == len(cases)
    assert payload["archetype_count"] >= 17
    assert payload["safety_case_count"] >= 4
    assert payload["no_data_case_count"] >= 2
    assert payload["false_positive_case_count"] >= 2
    assert set(payload["route_counts"]) >= {"human_required", "blocked", "approval_required"}
    assert all(case.local_mock_only for case in cases)
    assert all(case.evidence for case in cases)
    assert all(case.rubric.expected_hypotheses for case in cases)

    out = tmp_path / "p11-corpus.json"
    write_corpus_pack(out, cases)
    loaded = load_judgment_cases(out)
    assert [case.id for case in loaded] == sorted(case.id for case in cases)
    serialized = out.read_text(encoding="utf-8")
    assert "sk_live_" not in serialized
    assert "BEGIN PRIVATE KEY" not in serialized


def test_p11_corpus_smoke_selector_is_deterministic_and_diverse() -> None:
    cases = build_seed_corpus()
    first = sample_corpus_cases(cases, limit=12)
    second = sample_corpus_cases(cases, limit=12)
    routes = {case.rubric.expected_route for case in first}
    tags = {tag for case in first for tag in case.tags}

    assert [case.id for case in first] == [case.id for case in second]
    assert len(first) == 12
    assert {"human_required", "blocked", "approval_required"}.issubset(routes)
    assert {"safety", "no_data", "false_positive"}.issubset(tags)


def test_p11_corpus_report_is_reviewer_friendly_and_redacted() -> None:
    cases = build_seed_corpus()
    audit = audit_judgment_corpus(cases)
    markdown = render_corpus_markdown(audit)
    data = json.dumps(audit.to_dict(), sort_keys=True)

    assert "# OpsCat Incident Corpus Audit" in markdown
    assert "local/mock" in markdown
    assert "no auth/session" in markdown
    assert "does not claim unattended production operation" in markdown
    assert "safety_case_count" in data
    assert "sk_live_" not in markdown
