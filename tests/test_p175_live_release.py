from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.services.p147_p152_contracts import with_self_hash
from app.services.p175_live_release import (
    EXPECTED_HARNESS_MANIFEST_HASH,
    EXPECTED_P175_PLAN_HASH,
    QUALIFIED_RUN_ID,
    P175LiveReleaseError,
    QualifiedRun,
    assemble_release_evidence,
    build_release_evidence,
    load_qualified_run,
    validate_release_evidence,
)

ROOT = Path(__file__).resolve().parents[1]


def _external_review(run: QualifiedRun) -> dict[str, object]:
    value = {
        "schema_version": "p175.final_implementation_review.v1",
        "phase": "p175",
        "decision": "approve",
        "writer_id": "019f747c-9c72-7e30-ab40-af1cb23330fd",
        "reviewer_id": "019f7486-f68b-77a3-adc1-20d19eecf344",
        "reviewer_identity": "code-reviewer",
        "review_source": "codex_native_subagent",
        "reviewed_at": "2026-07-18T09:00:00Z",
        "findings": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
        "limitations": [
            "binds_existing_p175_live_harness_run_no_new_live_operation",
            "disposable_p174_gcp_lab_only_not_customer_production",
            "p176_requires_this_canonical_closeout_before_predecessor_acceptance",
        ],
        "reviewed_run": {
            "qualified_run_id": run.run_id,
            "summary_file_hash": run.summary_file_hash,
            "jsonl_file_hash": run.jsonl_file_hash,
            "jsonl_hash": run.verified_jsonl["jsonl_hash"],
            "tail_hash": run.verified_jsonl["tail_hash"],
        },
        "reviewed_plan_hash": EXPECTED_P175_PLAN_HASH,
        "reviewed_harness_manifest_hash": EXPECTED_HARNESS_MANIFEST_HASH,
    }
    return with_self_hash(value, "review_hash")


def test_release_evidence_binds_exact_qualified_run_plan_harness_sources_and_review() -> None:
    run = load_qualified_run(ROOT)
    review = _external_review(run)
    release = assemble_release_evidence(run, review, project_root=ROOT)

    assert release["schema_version"] == "p175.release_evidence.v1"
    assert release["phase"] == "p175"
    assert release["status"] == "p175_live_qualification_closed_out"
    assert release["predecessor_closeout"]["qualified_run_id"] == QUALIFIED_RUN_ID
    assert release["predecessor_closeout"]["summary"]["qualified"] is True
    assert release["predecessor_closeout"]["derivative_provenance"] == {
        "source": "p174_security_quarantine",
        "redaction_profile": "p175_predecessor_derivative_v1",
        "raw_payload_removed": True,
        "outcome_semantics_preserved": True,
        "original_summary_file_hash": "sha256:b84ba7feafe6df399603441f01919de16b328138f477213244b9e3b18972a7de",
        "original_jsonl_file_hash": "sha256:05ce6e2f466ef578722d172ab8784a0af52269347e5dc77ba54f3b71a3ce8177",
        "original_jsonl_hash": "sha256:c316df1189424e34f81eaaff020ce047fab00d2918b5022fabfa88ef775c3461",
        "original_tail_hash": "sha256:edd5216b82fdebe08a76b23df7503de6d59b15ce003d0bc8d48482228adeb159",
    }
    assert release["predecessor_closeout"]["summary"]["gates"]["healthy_window"]["observed_consecutive"] == 200
    assert release["predecessor_closeout"]["summary"]["gates"]["scenario_campaign"]["observed_successful"] == 100
    assert release["predecessor_closeout"]["evidence_jsonl"]["event_count"] == 301
    assert release["plan_hash"] == EXPECTED_P175_PLAN_HASH
    assert release["harness_manifest_hash"] == EXPECTED_HARNESS_MANIFEST_HASH
    assert release["review"]["decision"] == "approve"
    assert release["review"]["reviewer_id"] != release["review"]["writer_id"]
    assert set(release["source_hashes"]) == {
        "app/services/p175_live_release.py",
        "scripts/finalize_p175_live_release.py",
        "tests/test_p175_live_release.py",
        "docs/tickets/p175/README.md",
    }
    assert validate_release_evidence(release, project_root=ROOT)["status"] == release["status"]


def test_summary_tampering_fails_closed(tmp_path: Path) -> None:
    source = ROOT / "evals/p174/live" / QUALIFIED_RUN_ID
    run_dir = tmp_path / QUALIFIED_RUN_ID
    run_dir.mkdir()
    (run_dir / "p175-live-evidence.jsonl").write_text((source / "p175-live-evidence.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    summary = json.loads((source / "p175-live-summary.json").read_text(encoding="utf-8"))
    summary["evidence"]["tail_hash"] = "sha256:" + "0" * 64
    (run_dir / "p175-live-summary.json").write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")

    with pytest.raises(P175LiveReleaseError, match="summary_chain_mismatch"):
        load_qualified_run(tmp_path)


def test_nonqualified_summary_fails_closed(tmp_path: Path) -> None:
    source = ROOT / "evals/p174/live" / QUALIFIED_RUN_ID
    run_dir = tmp_path / QUALIFIED_RUN_ID
    run_dir.mkdir()
    (run_dir / "p175-live-evidence.jsonl").write_text((source / "p175-live-evidence.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    summary = json.loads((source / "p175-live-summary.json").read_text(encoding="utf-8"))
    summary["qualified"] = False
    summary["status"] = "blocked"
    (run_dir / "p175-live-summary.json").write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")

    with pytest.raises(P175LiveReleaseError, match="summary_not_qualified"):
        load_qualified_run(tmp_path)


def test_jsonl_chain_tampering_fails_closed(tmp_path: Path) -> None:
    source = ROOT / "evals/p174/live" / QUALIFIED_RUN_ID
    run_dir = tmp_path / QUALIFIED_RUN_ID
    run_dir.mkdir()
    (run_dir / "p175-live-summary.json").write_text((source / "p175-live-summary.json").read_text(encoding="utf-8"), encoding="utf-8")
    lines = (source / "p175-live-evidence.jsonl").read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[1])
    event["previous_hash"] = "sha256:" + "0" * 64
    lines[1] = json.dumps(event, sort_keys=True)
    (run_dir / "p175-live-evidence.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(P175LiveReleaseError, match="evidence_chain_invalid"):
        load_qualified_run(tmp_path)


def test_missing_review_fails_closed() -> None:
    release = build_release_evidence(_external_review(load_qualified_run(ROOT)), ROOT)
    tampered = deepcopy(release)
    tampered.pop("review")
    tampered["evidence_hash"] = release["evidence_hash"]

    with pytest.raises(P175LiveReleaseError, match="review_missing"):
        validate_release_evidence(tampered, project_root=ROOT)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("predecessor_closeout", "summary", "qualified"), False),
        (("predecessor_closeout", "summary", "manifest_hash"), "sha256:" + "0" * 64),
        (("predecessor_closeout", "evidence_jsonl", "event_count"), 300),
        (("predecessor_closeout", "derivative_provenance", "raw_payload_removed"), False),
        (("metrics", "healthy_windows"), 199),
    ],
)
def test_rehashed_embedded_closeout_tampering_fails_closed(path: tuple[str, ...], value: object) -> None:
    release = build_release_evidence(_external_review(load_qualified_run(ROOT)), ROOT)
    tampered = deepcopy(release)
    target = tampered
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    tampered["evidence_hash"] = with_self_hash(tampered, "evidence_hash")["evidence_hash"]
    with pytest.raises(P175LiveReleaseError, match="derived_facts"):
        validate_release_evidence(tampered, project_root=ROOT)
