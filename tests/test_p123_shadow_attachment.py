from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.p123_shadow_attachment import (
    P123ShadowAttachmentError,
    build_release_evidence,
    run_shadow_attachment,
    write_default_inputs,
    zero_authority_counters,
)


def _fixture(tmp_path: Path) -> Path:
    manifest = tmp_path / "manifest.json"
    write_default_inputs(manifest)
    return manifest


def test_shadow_attachment_promotes_deterministic_read_only_replay(tmp_path: Path) -> None:
    manifest = _fixture(tmp_path)

    first = run_shadow_attachment(manifest_path=manifest)
    second = run_shadow_attachment(manifest_path=manifest)
    evidence = build_release_evidence(first)

    assert first == second
    assert first["record_count"] >= 100
    assert len(first["telemetry_families"]) >= 3
    assert first["metrics"]["hash_validation_rate"] == 1.0
    assert first["metrics"]["redaction_metadata_validation_rate"] == 1.0
    assert first["metrics"]["deterministic_replay_rate"] == 1.0
    assert first["metrics"]["dropped_record_count"] == 0
    assert first["metrics"]["duplicated_record_count"] == 0
    assert first["metrics"]["evidence_citation_rate"] == 1.0
    assert first["metrics"]["network_call_count"] == 0
    assert first["authority"]["counters"] == zero_authority_counters()
    assert evidence["release_status"] == "p123_read_only_shadow_replay_promoted"
    assert all(evidence["gates"].values())


@pytest.mark.parametrize(
    ("patch", "expected"),
    [
        ({"authority_counters": {**zero_authority_counters(), "live_connector_call_count": 1}}, "nonzero_authority_counter"),
        ({"hash_manifest": None}, "missing_artifact_hash_manifest"),
        ({"redaction_metadata": {"status": "missing", "secret_scan": "failed"}}, "missing_redaction_metadata"),
        ({"records_path": "https://example.invalid/telemetry.jsonl"}, "remote_or_unsafe_records_path"),
        ({"claim_controls": {"scope": "this is live production proof"}}, "recorded_replay_claimed_as_live_proof"),
        ({"provenance": {"credentialed": True, "live_connector": False, "mutation_authority": False}}, "missing_provenance"),
    ],
)
def test_manifest_red_cases_fail_closed(tmp_path: Path, patch: dict[str, object], expected: str) -> None:
    manifest = _fixture(tmp_path)
    data = json.loads(manifest.read_text())
    data.update(patch)
    manifest.write_text(json.dumps(data, sort_keys=True))

    with pytest.raises(P123ShadowAttachmentError, match=expected):
        run_shadow_attachment(manifest_path=manifest)


def test_record_secret_and_hash_drift_fail_closed(tmp_path: Path) -> None:
    manifest = _fixture(tmp_path)
    telemetry = tmp_path / "telemetry.jsonl"
    rows = [json.loads(line) for line in telemetry.read_text().splitlines()]
    rows[0]["message"] = "password=not-allowed"
    telemetry.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))

    with pytest.raises(P123ShadowAttachmentError, match="replay_hash_drift"):
        run_shadow_attachment(manifest_path=manifest)


def test_recorded_replay_outputs_are_observational_only(tmp_path: Path) -> None:
    report = run_shadow_attachment(manifest_path=_fixture(tmp_path))

    assert report["capability_matrix"]["credentialed_live_connector_evidence"] is False
    assert all(judgment["route"] == "observe_only" for judgment in report["shadow_judgments"])
    assert all(judgment["executed_action"] is False for judgment in report["shadow_judgments"])
