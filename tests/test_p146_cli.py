from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fixtures.p146.builders import build_known_conformance_corpus


def test_cli_writes_portable_bounded_episode_artifacts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.p146_live_shadow_cli import main

    profile = tmp_path / "profile.json"
    output = tmp_path / "episode"
    profile.write_text(json.dumps({"schema_version": "p146.release_profile.v1", "corpus": build_known_conformance_corpus()}, default=sorted), encoding="utf-8")

    import app.services.p146_live_shadow as core

    def missing_instrumentation(_visible_case: object) -> dict[str, object]:
        return {
            "schema_version": "p146.live_shadow_episode.v1",
            "prediction": {"schema_version": "p146.shadow_prediction.v1", "prediction_hash": "sha256:" + "0" * 64},
            "aggregate_counters": {},
        }

    with monkeypatch.context() as scoped:
        scoped.setattr(core, "run_live_shadow_episode", missing_instrumentation)
        blocked_output = tmp_path / "blocked-episode"
        assert main(["run", "--profile", str(profile), "--output", str(blocked_output), "--case", "p146-case-01"]) == 1
        error_payload = json.loads(capsys.readouterr().err)
        assert error_payload["status"] == "blocked"
        assert "receipt" in error_payload["error"].lower() or "counter" in error_payload["error"].lower()

    assert main(["run", "--profile", str(profile), "--output", str(output), "--case", "p146-case-01"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "p146.cli_episode_receipt.v1"
    assert payload["artifact_root"] == "episode"
    assert payload["authority_counters"]["credential_read_count"] == 0
    assert payload["authority_counters"]["external_http_count"] == 0
    assert "://" not in json.dumps(payload, sort_keys=True)
    assert str(tmp_path) not in json.dumps(payload, sort_keys=True)
    prediction_artifact = json.loads((output / "prediction.json").read_text(encoding="utf-8"))
    receipts_artifact = json.loads((output / "receipts.json").read_text(encoding="utf-8"))
    assert set(prediction_artifact) == {
        "schema_version",
        "case_ref_hash",
        "incident_detected",
        "diagnostic_disposition",
        "ranked_hypotheses",
        "p14_route",
        "final_shadow_route",
        "safety_overlay",
        "citations",
        "missing_providers",
        "executed_actions",
        "runtime_counters",
        "forbidden_counters",
        "prediction_hash",
    }
    assert [receipt["schema_version"] for receipt in receipts_artifact["request_receipts"]] == ["p146.http_request_receipt.v1"] * 3
    assert [receipt["schema_version"] for receipt in receipts_artifact["response_receipts"]] == ["p146.http_response_receipt.v1"] * 3
    assert receipts_artifact["aggregate_counters"]["runtime"]["loopback_socket_attempt_count"] == len(receipts_artifact["request_receipts"])
    assert receipts_artifact["aggregate_counters"]["runtime"]["complete_response_count"] == sum(
        1 for receipt in receipts_artifact["response_receipts"] if receipt["complete"] is True
    )
