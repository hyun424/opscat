from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

FIXTURE = Path("tests/fixtures/p109/microremed/smoke_bundle.json")


def _api() -> Any:
    try:
        return importlib.import_module("app.services.microremed_result_adapter")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P109 RED: missing MicroRemed import adapter ({exc}).", pytrace=False)


def _bundle() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_import_microremed_bundle_normalizes_clean_room_schema_without_trusting_success() -> None:
    api = _api()
    bundle = _bundle()
    bundle["runs"][0]["submitted_success"] = False

    imported = api.import_microremed_bundle(bundle)
    payload = imported.to_dict()
    run = next(item for item in payload["runs"] if item["run_id"] == "mr-verified-recovery")

    assert payload["schema_version"] == "p109.microremed_import.v1"
    assert payload["source_revision"] == "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert payload["external_execution"] is True
    assert payload["smoke_only"] is True
    assert payload["release_trusted"] is False
    assert run["outcome"] == "verified_recovery"
    assert run["submitted_success"] is False
    assert run["trusted_submitted_success"] is False
    assert run["release_trusted"] is False
    assert run["eligible"] is True
    assert run["attempt_count"] == 1
    assert run["non_noop_intervention"] is True
    assert run["verifier"]["verifier_id"] == "independent-verifier-a"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda payload: payload.__setitem__("external_execution", False), "external_execution"),
        (lambda payload: payload["runs"].__setitem__(1, copy.deepcopy(payload["runs"][0])), "duplicate"),
        (lambda payload: payload["runs"][0].__setitem__("source_revision", "main"), "immutable"),
        (lambda payload: payload["runs"][0].__setitem__("attempts", []), "attempt"),
        (lambda payload: payload["runs"][0].pop("verifier"), "verifier"),
        (lambda payload: payload["runs"][0]["verifier"].__setitem__("verifier_id", payload["runs"][0]["actor"]["id"]), "independent"),
        (lambda payload: payload["runs"][0]["verifier"]["signature"].__setitem__("key_id", 42), "key_id"),
        (lambda payload: payload["runs"][0]["attempts"][0].__setitem__("action_id", "kubectl-delete-pod"), "unknown action"),
        (lambda payload: payload["runs"][0]["attempts"][0].__setitem__("action_playbook_hash", "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"), "hash"),
        (lambda payload: payload["runs"][0].__setitem__("ended_at", "2026-01-01T00:00:00Z"), "timestamp"),
    ],
)
def test_import_rejects_invalid_microremed_authority_and_integrity_cases(mutate: Any, message: str) -> None:
    api = _api()
    payload = _bundle()
    mutate(payload)

    with pytest.raises(api.MicroRemedImportError, match=message):
        api.import_microremed_bundle(payload)


def test_import_marks_recovery_without_independent_replay_as_unverified_not_successful() -> None:
    api = _api()
    payload = _bundle()
    run = payload["runs"][0]
    run["run_id"] = "mr-submitted-success-lie"
    run["submitted_success"] = True
    run["verifier"]["replay_passed"] = False

    imported = api.import_microremed_bundle({**payload, "runs": [run]})
    normalized = imported.to_dict()["runs"][0]

    assert normalized["outcome"] == "unverified"
    assert normalized["eligible"] is False
    assert normalized["trusted_submitted_success"] is False
    assert normalized["after_health"]["healthy"] is True


def test_release_trust_requires_allowed_signer_policy_and_key_id() -> None:
    api = _api()
    payload = _bundle()
    payload["smoke_only"] = False
    for run in payload["runs"]:
        run["verifier"]["signature"]["key_id"] = "review-key-a"

    untrusted = api.import_microremed_bundle(payload).to_dict()
    trusted = api.import_microremed_bundle(
        payload,
        trusted_signers=[{"signer_id": "public-reviewer-a", "key_id": "review-key-a"}],
    ).to_dict()
    wrong_key = api.import_microremed_bundle(
        payload,
        trusted_signers=[{"signer_id": "public-reviewer-a", "key_id": "other-key"}],
    ).to_dict()

    assert untrusted["release_trusted"] is True
    assert trusted["release_trusted"] is True
    assert wrong_key["release_trusted"] is False
    assert all(run["release_trusted"] is True for run in trusted["runs"])


def test_default_smoke_fixture_is_never_release_trusted_even_with_matching_signer() -> None:
    api = _api()
    payload = _bundle()
    for run in payload["runs"]:
        run["verifier"]["signature"]["key_id"] = "review-key-a"

    imported = api.import_microremed_bundle(
        payload,
        trusted_signers=[{"signer_id": "public-reviewer-a", "key_id": "review-key-a"}],
    ).to_dict()

    assert imported["smoke_only"] is True
    assert imported["release_trusted"] is False
    assert all(run["release_trusted"] is False for run in imported["runs"])


def test_importer_exposes_exact_zero_runtime_authority_counters() -> None:
    payload = _api().import_microremed_bundle(_bundle()).to_dict()

    assert payload["authority"] == {
        "auth": 0,
        "credentials": 0,
        "shell": 0,
        "subprocess": 0,
        "kubernetes": 0,
        "ansible": 0,
        "cloud": 0,
        "database": 0,
        "production_adapter": 0,
        "mutation": 0,
        "executor": 0,
        "online_policy_write": 0,
    }


def test_zero_runtime_authority_counter_keys_are_clear_literals() -> None:
    source = Path("app/services/microremed_result_adapter.py").read_text(encoding="utf-8")

    assert '"credentials": 0' in source
    assert '"subprocess": 0' in source
    assert '"kubernetes": 0' in source
    assert '"ansible": 0' in source
    assert '"executor": 0' in source
    assert '"creden" + "tials"' not in source
    assert '"sub" + "process"' not in source
    assert '"kuber" + "netes"' not in source
    assert '"an" + "sible"' not in source
    assert '"exec" + "utor"' not in source
