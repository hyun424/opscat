from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.services.p153_staging_shadow import (
    P153StagingShadowError,
    RecordedReadOnlyTransport,
    assemble_p153_release_evidence,
    build_p153_final_review,
    build_p153_freeze_manifest,
    load_p153_profile,
    run_p153_shadow_cycle,
    validate_p153_release_evidence,
)

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "evals/p153/input/staging-shadow-profile.json"


def _profile() -> dict:
    return json.loads(PROFILE.read_text(encoding="utf-8"))


def test_contract_and_predecessor_fail_closed(tmp_path: Path) -> None:
    profile = _profile()
    profile["environment"] = "production"
    with pytest.raises(P153StagingShadowError, match="staging"):
        run_p153_shadow_cycle(project_root=ROOT, profile=profile, output_dir=tmp_path)

    profile = _profile()
    profile["sources"][0]["method"] = "POST"
    with pytest.raises(P153StagingShadowError, match="GET"):
        run_p153_shadow_cycle(project_root=ROOT, profile=profile, output_dir=tmp_path)

    profile = _profile()
    profile["sources"][0]["path"] = "/api/v1/admin/delete"
    with pytest.raises(P153StagingShadowError, match="path"):
        run_p153_shadow_cycle(project_root=ROOT, profile=profile, output_dir=tmp_path)

    profile = _profile()
    profile["sources"][2]["path"] = "/api/0/admin/"
    with pytest.raises(P153StagingShadowError, match="path"):
        run_p153_shadow_cycle(project_root=ROOT, profile=profile, output_dir=tmp_path)

    profile = _profile()
    profile["sources"][0]["endpoint"] = "https://prometheus.staging.internal/embedded/path"
    with pytest.raises(P153StagingShadowError, match="host"):
        run_p153_shadow_cycle(project_root=ROOT, profile=profile, output_dir=tmp_path)

    profile = _profile()
    profile["sources"][0]["credential_env"] = "raw-secret-value"
    with pytest.raises(P153StagingShadowError, match="credential"):
        run_p153_shadow_cycle(project_root=ROOT, profile=profile, output_dir=tmp_path)


def test_happy_path_investigates_and_builds_grounded_judgment(tmp_path: Path) -> None:
    profile = load_p153_profile(PROFILE)
    transport = RecordedReadOnlyTransport.from_profile(profile)
    report = run_p153_shadow_cycle(
        project_root=ROOT,
        profile=profile,
        output_dir=tmp_path,
        transport=transport,
    )

    assert report["status"] == "p153_staging_read_only_shadow_qualified"
    assert report["summary"]["source_count"] == 3
    assert report["summary"]["successful_source_count"] == 3
    assert report["summary"]["normalized_evidence_count"] >= 5
    assert report["judgment"]["outcome"] == "incident_likely"
    assert report["judgment"]["top_hypothesis"] == "recent_deploy_regression"
    assert report["judgment"]["supporting_provider_count"] >= 2
    assert len(report["judgment"]["citations"]) >= 3
    assert report["audit"]["real_network_call_count"] == 0
    assert report["audit"]["transport_call_count"] == 4
    assert report["audit"]["retry_count"] == 1
    assert report["audit"]["action_execution_count"] == 0
    assert report["audit"]["production_mutation_count"] == 0
    serialized = json.dumps(report)
    assert "fixture-secret" not in serialized
    assert "public:secret" not in serialized
    assert "fixture-label-secret" not in serialized
    assert "fixture-password" not in serialized


def test_missing_evidence_abstains_and_resume_is_deduplicated(tmp_path: Path) -> None:
    profile = _profile()
    profile["sources"] = profile["sources"][:1]
    profile["limits"]["max_sources"] = 1
    first = run_p153_shadow_cycle(
        project_root=ROOT,
        profile=profile,
        output_dir=tmp_path,
        transport=RecordedReadOnlyTransport.from_profile(profile),
    )
    second = run_p153_shadow_cycle(
        project_root=ROOT,
        profile=profile,
        output_dir=tmp_path,
        transport=RecordedReadOnlyTransport.from_profile(profile),
    )

    assert first["judgment"]["outcome"] == "insufficient_evidence"
    assert first["judgment"]["top_hypothesis"] is None
    assert first["judgment"]["evidence_requests"]
    assert second["summary"]["resume_count"] == 1
    assert second["summary"]["new_evidence_count"] == 0
    assert second["summary"]["duplicate_evidence_count"] == first["summary"]["normalized_evidence_count"]

    state_path = tmp_path / "shadow-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["generation"] = 0
    state_path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(P153StagingShadowError, match="state"):
        run_p153_shadow_cycle(
            project_root=ROOT,
            profile=profile,
            output_dir=tmp_path,
            transport=RecordedReadOnlyTransport.from_profile(profile),
        )


def test_live_boundary_redaction_and_budget_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile = _profile()
    profile["sources"][0]["endpoint"] = "http://prometheus.staging.internal"
    with pytest.raises(P153StagingShadowError, match="HTTPS"):
        run_p153_shadow_cycle(
            project_root=ROOT,
            profile=profile,
            output_dir=tmp_path,
            mode="live",
            transport=RecordedReadOnlyTransport.from_profile(profile),
        )

    profile = _profile()
    with pytest.raises(P153StagingShadowError, match="acknowledgement"):
        run_p153_shadow_cycle(
            project_root=ROOT,
            profile=profile,
            output_dir=tmp_path,
            mode="live",
            transport=RecordedReadOnlyTransport.from_profile(profile),
        )

    monkeypatch.setenv("OPSCAT_STAGING_SHADOW_ACK", "read-only-staging")
    profile["limits"]["max_response_bytes"] = 99_999_999
    with pytest.raises(P153StagingShadowError, match="budget"):
        run_p153_shadow_cycle(
            project_root=ROOT,
            profile=profile,
            output_dir=tmp_path,
            mode="live",
            transport=RecordedReadOnlyTransport.from_profile(profile),
        )


def test_release_evidence_requires_zero_finding_review(tmp_path: Path) -> None:
    profile = load_p153_profile(PROFILE)
    report = run_p153_shadow_cycle(
        project_root=ROOT,
        profile=profile,
        output_dir=tmp_path,
        transport=RecordedReadOnlyTransport.from_profile(profile),
    )
    freeze = build_p153_freeze_manifest(project_root=ROOT, report=report)
    review = build_p153_final_review(
        report=report,
        freeze_manifest=freeze,
        writer_agent_id="019f6a00-0000-7000-8000-000000000001",
        reviewer_agent_id="019f6a00-0000-7000-8000-000000000002",
        reviewer_identity="p153-writer-separated-reviewer",
        reviewed_at="2026-07-16T12:00:00Z",
    )
    evidence = assemble_p153_release_evidence(report=report, freeze_manifest=freeze, final_review=review)
    assert validate_p153_release_evidence(evidence, project_root=ROOT)["release_status"] == "p153_staging_shadow_runtime_ready"

    bad_review = deepcopy(review)
    bad_review["findings"]["p2"] = 1
    with pytest.raises(P153StagingShadowError, match="findings"):
        assemble_p153_release_evidence(report=report, freeze_manifest=freeze, final_review=bad_review)

    non_utc_review = deepcopy(review)
    non_utc_review["reviewed_at"] = "2026-07-16T12:00:00+09:00"
    with pytest.raises(P153StagingShadowError, match="UTC"):
        assemble_p153_release_evidence(report=report, freeze_manifest=freeze, final_review=non_utc_review)

    stale = deepcopy(evidence)
    stale["report_hash"] = "sha256:" + "0" * 64
    with pytest.raises(P153StagingShadowError):
        validate_p153_release_evidence(stale, project_root=ROOT)
