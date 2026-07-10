from __future__ import annotations

import hashlib
import importlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests.fixtures.p106_p105_release_archive import P105_REAL_DERIVED_ARCHIVE, safe_extract_p105_release_archive

PLANNER_CASES = Path("evals/prevention/p106_planner_cases.json")


def _api() -> Any:
    try:
        return importlib.import_module("app.services.preventive_action_planner")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P106 RED: missing preventive action planner module ({exc}).", pytrace=False)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _planner(api: Any) -> Any:
    cls = getattr(api, "PreventiveActionPlanner", None)
    if cls is None:
        pytest.fail("P106 RED: expose PreventiveActionPlanner.", pytrace=False)
    return cls()


def _cases() -> list[dict[str, Any]]:
    return list(json.loads(PLANNER_CASES.read_text(encoding="utf-8"))["cases"])


def _write_path_validated_p105_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    artifact = tmp_path / "p105-release-qualified.json"
    artifact.write_text(
        json.dumps(
            {
                "schema_version": "p105.release_qualified.fixture.v1",
                "run_id": "p105-qualified",
                "authority": {
                    "auth_enabled": False,
                    "production_mutation_enabled": False,
                    "action_authority": False,
                    "remediation_execution_enabled": False,
                    "default_external_model_calls": 0,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()

    def validate_artifact(path: str | Path) -> dict[str, Any]:
        requested = Path(path)
        assert requested == artifact
        return {
            "validation_error_codes": [],
            "artifact_identity": {
                "path": str(artifact),
                "sha256": digest,
                "root_hash": digest,
                "run_timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            },
            "artifact_manifests": {
                "rows": {"path": str(artifact), "sha256": digest, "referenced_by_benchmark_payload": True},
                "benchmark": {"path": str(artifact), "sha256": digest, "referenced_by_benchmark_payload": True},
            },
            "authority": {
                "auth_enabled": False,
                "production_mutation_enabled": False,
                "action_authority": False,
                "remediation_execution_enabled": False,
                "default_external_model_calls": 0,
            },
            "release_gate": {
                "release_qualified": True,
                "p106_unlocked": True,
                "held_out_calibration": {"pass": True},
                "families": {
                    "database": {"pass": True},
                    "deploy": {"pass": True},
                    "queue": {"pass": True},
                },
                "global": {"pass": True},
                "real_derived_transfer": {"pass": True},
                "safety_boundary": {"pass": True},
            },
        }

    prereq_api = importlib.import_module("app.services.p105_release_prerequisite")
    monkeypatch.setattr(prereq_api, "validate_p105_release_qualified_artifact", validate_artifact)
    return artifact


def test_committed_planner_cases_keep_scorer_labels_out_of_public_context() -> None:
    payload = json.loads(PLANNER_CASES.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "p106.planner_cases.v1"
    for case in payload["cases"]:
        public_text = json.dumps({key: value for key, value in case.items() if not key.startswith("scorer_only")}, sort_keys=True)
        assert "scorer_only" not in public_text
        assert "expected_capability" not in public_text


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["case_id"])
def test_planner_selects_expected_fallback_or_simulation_only_plan(
    case: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api = _api()
    if case["expected_route"] == "plan":
        case = dict(case)
        case["p105_artifact_path"] = str(_write_path_validated_p105_artifact(tmp_path, monkeypatch))
        monkeypatch.setattr(api, "_registry_hash_parity", lambda composition: bool(_get(composition, "registry_hash_parity")), raising=False)

    result = _planner(api).plan(case)

    assert _get(result, "route") == case["expected_route"]
    assert _get(result, "execution_enabled") is False
    assert _get(result, "simulation_only") is True
    assert _get(result, "p107_required_for_execution") is True
    assert _get(result, "reasons", _get(result, "operator_reasons", []))
    if case["expected_route"] == "plan":
        selected = _get(result, "selected_candidate")
        assert _get(selected, "evidence_links")
        assert _get(selected, "simulation_result") is not None
        assert _get(selected, "policy_decision") is not None
        assert _get(selected, "canary_contract") is not None
        assert _get(selected, "rollback_trigger")
        assert _get(selected, "post_checks")


@pytest.mark.parametrize(
    ("patch", "reason"),
    [
        ({"p104_evidence": {"sufficient_for_policy_handoff": False, "evidence_ids": []}}, "p104"),
        ({"p104_evidence": {"sufficient_for_policy_handoff": True, "evidence_ids": ["ev"], "fresh": False}}, "p104"),
        ({"forecast": {"probability": 0.2, "avoided_impact": 20.0, "uncertainty": 0.1, "false_alert_denominator": 20}}, "probability"),
        ({"advisory_capabilities": ["unknown.capability"]}, "capability"),
    ],
)
def test_planner_fails_closed_before_scoring_for_ineligible_inputs(patch: dict[str, Any], reason: str) -> None:
    case = dict(_cases()[0])
    for key, value in patch.items():
        case[key] = value

    result = _planner(_api()).plan(case)

    assert _get(result, "route") in {"observe", "escalate", "blocked_fail_closed"}
    assert reason in json.dumps(_get(result, "reasons", []), sort_keys=True)
    assert _get(result, "selected_candidate") in (None, {})


@pytest.mark.parametrize(
    "mutate",
    [
        lambda envelope: envelope.pop("schema_version"),
        lambda envelope: envelope.__setitem__("route", "inspect_next"),
        lambda envelope: envelope.__setitem__("fresh", False),
        lambda envelope: envelope["sufficiency_decision"].__setitem__("citation_evidence_ids", []),
        lambda envelope: envelope.__setitem__(
            "boundary",
            {"read_only_tools_only": True, "production_mutation_enabled": False, "action_authority": True},
        ),
    ],
)
def test_planner_rejects_noncanonical_or_forged_p104_handoff(mutate: Any) -> None:
    case = json.loads(json.dumps(_cases()[0]))
    mutate(case["p104_evidence"])

    result = _planner(_api()).plan(case)

    assert _get(result, "route") in {"observe", "escalate", "blocked_fail_closed"}
    assert _get(result, "selected_candidate") in (None, {})
    assert "p104" in json.dumps(_get(result, "reasons", []), sort_keys=True).lower()


def test_approval_metadata_cannot_flip_simulation_only_boundary() -> None:
    case = dict(_cases()[0])
    case["approval_profile"] = {
        "approved": True,
        "approval_id": "approval-p106-red",
        "capabilities": ["admin", "production:write"],
    }

    result = _planner(_api()).plan(case)

    assert _get(result, "execution_enabled") is False
    assert _get(result, "simulation_only") is True
    assert _get(result, "p107_required_for_execution") is True
    assert "approval-p106-red" in json.dumps(_get(result, "audit_context", {}), sort_keys=True)


def test_planner_has_no_test_only_policy_authority_override() -> None:
    api = _api()
    planner = _planner(api)

    result = planner.plan(_cases()[0])

    assert not hasattr(planner, "policy_decision_for_test")
    assert _get(result, "execution_enabled") is False
    assert _get(result, "simulation_only") is True
    assert _get(result, "p107_required_for_execution") is True


def test_planner_cannot_plan_without_path_validated_p105_prerequisite() -> None:
    case = dict(_cases()[0])
    case.pop("p105_artifact_path", None)
    case.pop("release_artifact_path", None)
    case.pop("p105_release_gate", None)
    case.pop("release_gate", None)
    case.pop("p105_prerequisite", None)

    result = _planner(_api()).plan(case)

    assert _get(result, "route") == "blocked_fail_closed"
    assert _get(result, "selected_candidate") in (None, {})
    assert "p105" in json.dumps(_get(result, "reasons", []), sort_keys=True).lower()


@pytest.mark.parametrize(
    "forged_gate",
    [
        {"release_qualified": True, "p106_unlocked": True, "validation_error_codes": []},
        {"release_qualified": True, "p106_unlocked": True, "artifact_identity": {"path": "forged"}},
    ],
)
def test_planner_rejects_forged_p105_booleans_without_canonical_artifact_validation(forged_gate: dict[str, Any]) -> None:
    case = dict(_cases()[0])
    case["p105_release_gate"] = forged_gate
    case.pop("p105_artifact_path", None)
    case.pop("release_artifact_path", None)

    result = _planner(_api()).plan(case)

    assert _get(result, "route") == "blocked_fail_closed"
    assert _get(result, "selected_candidate") in (None, {})
    assert "p105" in json.dumps(_get(result, "reasons", []), sort_keys=True).lower()


def test_planner_uses_registry_composition_and_shared_safety_gate_for_confidence_threshold(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api = _api()
    registry_api = importlib.import_module("app.services.preventive_capability_registry")
    gate_api = importlib.import_module("app.services.preventive_safety_gate")
    prereq_api = importlib.import_module("app.services.p105_release_prerequisite")
    artifact = tmp_path / "p105-qualified.json"
    artifact.write_text("{}", encoding="utf-8")
    case = dict(_cases()[0])
    case["p105_artifact_path"] = str(artifact)
    case["forecast"] = {**case["forecast"], "probability": 0.6}

    class PassingPrerequisite:
        def validate(self, _path: str) -> SimpleNamespace:
            return SimpleNamespace(release_qualified=True, p106_unlocked=True, downstream_allowed=True)

    composition_calls: list[Any] = []
    original_loader = registry_api.load_preventive_capability_registry

    def load_spy(*args: Any, **kwargs: Any) -> Any:
        composition = original_loader(*args, **kwargs)
        assert composition.policy_engine.risk_engine is composition.risk_engine
        assert composition.policy_engine.blast_radius_service.risk_engine is composition.risk_engine
        assert composition.policy_engine.action_simulator.risk_engine is composition.risk_engine
        composition_calls.append(composition)
        return composition

    gate_calls: list[dict[str, Any]] = []

    def gate_spy(candidate: dict[str, Any]) -> Any:
        gate_calls.append(candidate)
        assert candidate["confidence"] == 0.6
        assert candidate.get("confidence_threshold") == 0.8
        return SimpleNamespace(
            passed=False,
            route="observe",
            reasons=("confidence below preventive safety threshold",),
            to_dict=lambda: {
                "passed": False,
                "route": "observe",
                "reasons": ["confidence below preventive safety threshold"],
            },
        )

    monkeypatch.setattr(prereq_api, "P106ReleasePrerequisite", PassingPrerequisite)
    monkeypatch.setattr(registry_api, "load_preventive_capability_registry", load_spy)
    monkeypatch.setattr(gate_api, "evaluate_preventive_safety_gate", gate_spy)

    result = _planner(api).plan(case)

    assert composition_calls
    assert gate_calls
    assert _get(result, "route") in {"observe", "blocked_fail_closed"}
    assert _get(result, "selected_candidate") in (None, {})


def test_planner_real_happy_path_selects_safe_capability_with_canonical_registry_parity(tmp_path: Path) -> None:
    api = _api()
    artifact = safe_extract_p105_release_archive(P105_REAL_DERIVED_ARCHIVE, tmp_path / "p105-release")
    os.utime(artifact, None)
    case = dict(_cases()[0])
    case["p105_artifact_path"] = str(artifact)

    result = _planner(api).plan(case)

    assert _get(result, "route") == "plan"
    selected = _get(result, "selected_candidate")
    assert _get(selected, "capability_id") == case["scorer_only_expected_capability"]
    assert _get(selected, "registry_hash")
    assert _get(selected, "registry_hash") == _get(selected, "registry_parity_hash")
    assert _get(_get(selected, "safety_gate"), "passed") is True
    assert _get(selected, "execution_enabled") is False
    assert _get(selected, "simulation_only") is True
