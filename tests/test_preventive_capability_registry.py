from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

REGISTRY_FIXTURE = Path("evals/prevention/p106_capability_registry.json")
PROHIBITED_ACTION_TYPES = {"production.rollback", "production.restart_service", "database.mutate", "shell.execute", "cloud.delete_resource", "secret.read"}


def _api() -> Any:
    try:
        return importlib.import_module("app.services.preventive_capability_registry")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P106 RED: missing preventive capability registry module ({exc}).", pytrace=False)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _load(api: Any, path: Path = REGISTRY_FIXTURE) -> Any:
    loader = getattr(api, "load_preventive_capability_registry", None)
    if loader is None:
        pytest.fail("P106 RED: expose load_preventive_capability_registry(path).", pytrace=False)
    return loader(path)


def test_committed_registry_fixture_is_closed_local_and_simulation_safe() -> None:
    fixture = json.loads(REGISTRY_FIXTURE.read_text(encoding="utf-8"))

    assert fixture["schema_version"] == "p106.capability_registry.v1"
    assert fixture["authority"] == {
        "auth_enabled": False,
        "production_mutation_enabled": False,
        "action_authority": False,
        "remediation_execution_enabled": False,
        "default_external_model_calls": 0,
    }
    ids = [entry["capability_id"] for entry in fixture["capabilities"]]
    assert len(ids) == len(set(ids))
    for entry in fixture["capabilities"]:
        assert entry["action_type"] not in PROHIBITED_ACTION_TYPES
        assert "production" not in entry["environment_allowlist"]
        assert entry["required_evidence"]
        if entry["mutation_shaped"]:
            assert entry["canary_scope_template"]
            assert entry["rollback_trigger"]
            assert entry["post_checks"]
            assert entry["reversible"] is True


@pytest.mark.parametrize(
    ("case_id", "mutate", "reason"),
    [
        ("duplicate_ids", lambda data: data["capabilities"].append(dict(data["capabilities"][0])), "duplicate"),
        ("unresolved_action", lambda data: data["capabilities"][0].__setitem__("action_type", "unknown.provider.mutate"), "unknown.provider.mutate"),
        ("production_only", lambda data: data["capabilities"][0].__setitem__("environment_allowlist", ["production"]), "production"),
        ("missing_rollback", lambda data: data["capabilities"][2].__setitem__("rollback_trigger", None), "rollback"),
        ("shell_action", lambda data: data["capabilities"][0].__setitem__("action_type", "shell.execute"), "shell"),
        ("missing_evidence", lambda data: data["capabilities"][0].__setitem__("required_evidence", []), "evidence"),
    ],
)
def test_registry_load_fails_closed_for_invalid_capability_shapes(tmp_path: Path, case_id: str, mutate: Any, reason: str) -> None:
    api = _api()
    data = json.loads(REGISTRY_FIXTURE.read_text(encoding="utf-8"))
    mutate(data)
    path = tmp_path / f"{case_id}.json"
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    with pytest.raises((ValueError, AssertionError), match=reason):
        _load(api, path)


def test_registry_compiles_capability_to_action_request_and_policy_context() -> None:
    api = _api()
    composition = _load(api)
    compiler = getattr(composition, "compile_capability", getattr(api, "compile_preventive_capability", None))
    if compiler is None:
        pytest.fail("P106 RED: registry composition must compile capability to ActionRequest plus PolicyContext.", pytrace=False)

    compiled = compiler("preventive.mock.rollback_pr", service="payment-api", environment="staging", evidence_ids=["ev-1"])

    request = _get(compiled, "action_request", _get(compiled, "request"))
    context = _get(compiled, "policy_context", _get(compiled, "context"))
    assert _get(request, "action_type") == "mock.create_rollback_pr"
    assert _get(request, "environment") == "staging"
    assert _get(context, "environment") == "staging"
    assert _get(compiled, "execution_enabled") is False
    assert _get(compiled, "simulation_only") is True
    assert _get(compiled, "p107_required_for_execution") is True


def test_shared_risk_engine_identity_and_registry_hash_parity() -> None:
    composition = _load(_api())
    risk_engine = _get(composition, "risk_engine")
    policy_engine = _get(composition, "policy_engine")
    hashes = _get(composition, "registry_hashes", {})
    parity_hashes = _get(composition, "registry_parity_hashes", {})

    assert risk_engine is not None
    assert policy_engine is not None
    assert _get(policy_engine, "risk_engine") is risk_engine
    assert _get(_get(policy_engine, "blast_radius_service"), "risk_engine") is risk_engine
    assert _get(_get(policy_engine, "action_simulator"), "risk_engine") is risk_engine
    assert parity_hashes
    assert len(set(parity_hashes.values())) == 1
    assert _get(composition, "registry_hash") in set(parity_hashes.values())
    assert _get(composition, "registry_hash_parity") is True
    assert len(set(hashes.values())) > 1
    assert _get(composition, "registry_hash_mismatch_exposed") is True


def _canonical_hash(value: Any) -> str:
    normalized = json.loads(json.dumps(value, sort_keys=True, default=str))
    if isinstance(normalized, dict):
        normalized.pop("fixture_sha256", None)
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _metadata_projection(metadata: Any) -> dict[str, Any]:
    projected = asdict(metadata)
    projected["base_risk"] = str(metadata.base_risk)
    return projected


def test_registry_parity_hashes_are_independently_computed_and_not_overwritten() -> None:
    fixture = json.loads(REGISTRY_FIXTURE.read_text(encoding="utf-8"))
    composition = _load(_api())
    hashes = _get(composition, "registry_hashes", {})
    capabilities = _get(composition, "capabilities")
    risk_engine = _get(composition, "risk_engine")
    expected_fixture_hash = _canonical_hash(fixture)
    expected_capability_hash = _canonical_hash(
        {
            "capabilities": {key: asdict(value) for key, value in sorted(capabilities.items())},
            "actions": {
                capability.action_type: _metadata_projection(risk_engine.registry[capability.action_type])
                for capability in capabilities.values()
            },
        }
    )
    expected_risk_engine_hash = _canonical_hash(
        {key: _metadata_projection(value) for key, value in sorted(risk_engine.registry.items())}
    )

    assert hashes["fixture"] == expected_fixture_hash
    assert hashes["capability_registry"] == expected_capability_hash
    assert hashes["shared_risk_engine"] == expected_risk_engine_hash
    assert len({hashes["fixture"], hashes["capability_registry"], hashes["shared_risk_engine"]}) > 1


def test_registry_reports_hash_mismatch_instead_of_overwriting_it(tmp_path: Path) -> None:
    api = _api()
    data = json.loads(REGISTRY_FIXTURE.read_text(encoding="utf-8"))
    data["registry_id"] = "tampered-registry-id-that-does-not-change-capabilities"
    path = tmp_path / "tampered-registry.json"
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    composition = _load(api, path)
    hashes = _get(composition, "registry_hashes", {})

    assert hashes["fixture"] != hashes["capability_registry"]
    assert _get(composition, "registry_hash_mismatch_exposed") is True
