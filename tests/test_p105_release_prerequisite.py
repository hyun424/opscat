from __future__ import annotations

import copy
import hashlib
import importlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tests.fixtures.p106_p105_release_archive import P105_REAL_DERIVED_ARCHIVE, safe_extract_p105_release_archive

ZERO_AUTHORITY = {
    "auth_enabled": False,
    "production_mutation_enabled": False,
    "action_authority": False,
    "remediation_execution_enabled": False,
    "default_external_model_calls": 0,
}
REQUIRED_ROWS = {
    "held_out_calibration",
    "per_family_release_metrics",
    "global_release_metrics",
    "real_derived_transfer",
    "safety_boundary",
}
NOW = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


def _api() -> Any:
    try:
        return importlib.import_module("app.services.p105_release_prerequisite")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P106 RED: missing P105 prerequisite adapter module ({exc}).", pytrace=False)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _write_artifact(tmp_path: Path, payload: dict[str, Any] | None = None) -> Path:
    payload = payload or {"schema_version": "p105.release_qualified.fixture.v1", "run_id": "p105-qualified"}
    path = tmp_path / "p105-release-qualified.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _report(path: Path, *, timestamp: datetime | None = None) -> dict[str, Any]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "validation_error_codes": [],
        "artifact_identity": {
            "path": str(path),
            "sha256": digest,
            "root_hash": digest,
            "run_timestamp": (timestamp or NOW).isoformat().replace("+00:00", "Z"),
        },
        "artifact_manifests": {
            "rows": {"path": str(path), "sha256": digest, "referenced_by_benchmark_payload": True},
            "benchmark": {"path": str(path), "sha256": digest, "referenced_by_benchmark_payload": True},
        },
        "authority": dict(ZERO_AUTHORITY),
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


def _validate(adapter: Any, path: Path, **kwargs: Any) -> Any:
    for method_name in ("validate", "validate_artifact", "evaluate"):
        method = getattr(adapter, method_name, None)
        if callable(method):
            return method(path, **kwargs)
    pytest.fail("P106 RED: P106ReleasePrerequisite must expose validate(path).", pytrace=False)


def _adapter(api: Any) -> Any:
    cls = getattr(api, "P106ReleasePrerequisite", None)
    if cls is None:
        pytest.fail("P106 RED: expose P106ReleasePrerequisite.", pytrace=False)
    return cls(maximum_age=timedelta(hours=24), clock=lambda: NOW)


def _assert_blocked(result: Any, reason_fragment: str) -> None:
    assert _get(result, "release_qualified") is False
    assert _get(result, "p106_unlocked") is False
    reasons = json.dumps(_get(result, "reasons", _get(result, "failure_reasons", [])), sort_keys=True)
    assert reason_fragment in reasons
    assert _get(result, "downstream_allowed", False) is False


def test_accepts_only_validator_returned_canonical_p105_gate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    api = _api()
    artifact = _write_artifact(tmp_path)
    monkeypatch.setattr(api, "validate_p105_release_qualified_artifact", lambda path: _report(Path(path)))

    with pytest.raises(TypeError):
        _validate(_adapter(api), artifact, caller_gate={"release_qualified": False, "p106_unlocked": False})
    result = _validate(_adapter(api), artifact)

    assert _get(result, "release_qualified") is True
    assert _get(result, "p106_unlocked") is True
    evidence_map = _get(result, "evidence_map")
    assert set(_get(evidence_map, "rows", evidence_map).keys()) == REQUIRED_ROWS
    assert _get(result, "authority") == ZERO_AUTHORITY


def test_real_canonical_p105_artifact_unlocks_p106_then_rejects_tamper(tmp_path: Path) -> None:
    api = _api()
    artifact = safe_extract_p105_release_archive(P105_REAL_DERIVED_ARCHIVE, tmp_path / "p105-release")

    validator_report = api.validate_p105_release_qualified_artifact(artifact)
    assert validator_report["release_gate"]["release_qualified"] is True
    assert validator_report["release_gate"]["p106_unlocked"] is True
    assert validator_report["artifact_identity"]["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()

    adapter = api.P106ReleasePrerequisite(maximum_age=timedelta(days=30_000), clock=lambda: NOW)
    with pytest.raises(TypeError):
        _validate(adapter, artifact, caller_gate={"release_qualified": False, "p106_unlocked": False})
    result = _validate(adapter, artifact)

    assert _get(result, "release_qualified") is True
    assert _get(result, "p106_unlocked") is True
    assert _get(result, "artifact_identity")["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()

    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload["rows"][0]["public_features"]["tamper_probe"] = "changed-after-identity"
    artifact.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    tampered = _validate(adapter, artifact)

    _assert_blocked(tampered, "hash_mismatch")


@pytest.mark.parametrize(
    ("mutation", "expected_row"),
    [
        (lambda report: report["release_gate"].pop("held_out_calibration"), "held_out_calibration"),
        (lambda report: report["release_gate"].__setitem__("families", {}), "per_family_release_metrics"),
        (lambda report: report["release_gate"].__setitem__("families", {"database": {"pass": True}, "queue": {"pass": False}}), "per_family_release_metrics"),
        (lambda report: report["release_gate"].__setitem__("families", {"database": {}}), "per_family_release_metrics"),
        (lambda report: report["release_gate"].__setitem__("global", {"pass": False}), "global_release_metrics"),
        (lambda report: report["release_gate"].__setitem__("global", "true"), "global_release_metrics"),
        (lambda report: report["release_gate"].pop("real_derived_transfer"), "real_derived_transfer"),
        (lambda report: report["release_gate"].__setitem__("safety_boundary", {"pass": 1}), "safety_boundary"),
    ],
)
def test_rejects_each_missing_or_non_boolean_canonical_gate_row(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mutation: Any, expected_row: str) -> None:
    api = _api()
    artifact = _write_artifact(tmp_path)
    report = _report(artifact)
    mutation(report)
    report["release_gate"]["release_qualified"] = True
    report["release_gate"]["p106_unlocked"] = True
    monkeypatch.setattr(api, "validate_p105_release_qualified_artifact", lambda path: copy.deepcopy(report))

    result = _validate(_adapter(api), artifact)

    _assert_blocked(result, expected_row)


def test_rejects_misleading_raw_required_row_keys_when_canonical_paths_fail(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    api = _api()
    artifact = _write_artifact(tmp_path)
    report = _report(artifact)
    report["release_gate"]["families"] = {"database": {"pass": False}}
    report["release_gate"]["global"] = {}
    report["release_gate"]["per_family_release_metrics"] = {"pass": True}
    report["release_gate"]["global_release_metrics"] = {"pass": True}
    monkeypatch.setattr(api, "validate_p105_release_qualified_artifact", lambda path: copy.deepcopy(report))

    result = _validate(_adapter(api), artifact)

    _assert_blocked(result, "per_family_release_metrics")
    _assert_blocked(result, "global_release_metrics")


@pytest.mark.parametrize(
    "authority_patch",
    [
        {"action_authority": True},
        {"production_mutation_enabled": True},
        {"default_external_model_calls": 1},
        {"extra_scope": False},
    ],
)
def test_requires_exact_zero_authority_equality(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, authority_patch: dict[str, Any]) -> None:
    api = _api()
    artifact = _write_artifact(tmp_path)
    report = _report(artifact)
    report["authority"].update(authority_patch)
    monkeypatch.setattr(api, "validate_p105_release_qualified_artifact", lambda path: copy.deepcopy(report))

    result = _validate(_adapter(api), artifact)

    _assert_blocked(result, "authority")


def test_revalidates_identity_and_rejects_artifact_tamper(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    api = _api()
    artifact = _write_artifact(tmp_path)
    original_report = _report(artifact)

    def validator(path: Path) -> dict[str, Any]:
        current = _report(Path(path))
        if current["artifact_identity"]["sha256"] != original_report["artifact_identity"]["sha256"]:
            current["validation_error_codes"] = ["artifact_hash_changed"]
        return current

    monkeypatch.setattr(api, "validate_p105_release_qualified_artifact", validator)
    _validate(_adapter(api), artifact)
    artifact.write_text(json.dumps({"tampered": True}) + "\n", encoding="utf-8")

    result = _validate(_adapter(api), artifact)

    _assert_blocked(result, "artifact_hash_changed")


def test_rejects_stale_artifacts_with_injected_clock(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    api = _api()
    artifact = _write_artifact(tmp_path)
    stale_report = _report(artifact, timestamp=NOW - timedelta(days=2, seconds=1))
    monkeypatch.setattr(api, "validate_p105_release_qualified_artifact", lambda path: copy.deepcopy(stale_report))

    result = _validate(_adapter(api), artifact)

    _assert_blocked(result, "stale")


def test_forged_caller_payload_never_reaches_capability_compilation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    api = _api()
    artifact = _write_artifact(tmp_path)
    failed_report = _report(artifact)
    failed_report["release_gate"]["release_qualified"] = False
    failed_report["release_gate"]["p106_unlocked"] = False
    monkeypatch.setattr(api, "validate_p105_release_qualified_artifact", lambda path: copy.deepcopy(failed_report))
    called = False

    def compile_spy(*_args: Any, **_kwargs: Any) -> None:
        nonlocal called
        called = True

    with pytest.raises(TypeError):
        _validate(
            _adapter(api),
            artifact,
            caller_gate={"release_qualified": True, "p106_unlocked": True},
            downstream_compiler=compile_spy,
        )

    result = _validate(_adapter(api), artifact)
    _assert_blocked(result, "release_qualified")
    assert called is False
