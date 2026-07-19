#!/usr/bin/env python3
"""Run deterministic P176 live campaign qualification orchestration."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p147_p152_contracts import file_hash, stable_hash  # noqa: E402
from app.services.p176_campaign import generate_p176_campaign  # noqa: E402
from app.services.p176_live_bridge import (  # noqa: E402
    ADOPTION_BASELINE_BINDING_PATH,
    EPISODE_OBSERVATIONS_PATH,
    HEALTHY_WINDOW_OBSERVATIONS_PATH,
    P176LiveBridgeError,
    load_json,
    materialize_live_release_inputs,
    write_json,
)
from app.services.p176_live_gates import P176LiveGateError, validate_adoption_baseline_binding  # noqa: E402

STATE_SCHEMA_VERSION = "p176.live_campaign_state.v1"
READINESS_SCHEMA_VERSION = "p176.live_campaign_readiness.v1"
READINESS_STATUS = "p176_live_campaign_readiness_only"
INPUT_MANIFEST_PATH = ROOT / "evals/p176/input/manifest.json"
REVIEWED_PLAN_ARTIFACT_FIELDS = {
    "reviewed_apply_plan_artifact_path",
    "reviewed_teardown_plan_artifact_path",
    "reviewed_cost_cutoff_apply_plan_artifact_path",
    "reviewed_cost_cutoff_destroy_plan_artifact_path",
}
CAMPAIGN_MODES = ("fresh-lab", "p174-workload-adoption")


class P176LiveCampaignError(ValueError):
    """Raised when live campaign orchestration fails closed."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--state-path", type=Path)
    parser.add_argument("--mode", default="fresh-lab")
    parser.add_argument("--reviewed-apply-plan-artifact", type=Path)
    parser.add_argument("--reviewed-teardown-plan-artifact", type=Path)
    parser.add_argument("--reviewed-cost-cutoff-apply-plan-artifact", type=Path)
    parser.add_argument("--reviewed-cost-cutoff-destroy-plan-artifact", type=Path)
    args = parser.parse_args(argv)

    try:
        result = orchestrate_live_campaign(
            run_dir=args.run_dir,
            state_path=args.state_path,
            mode=args.mode,
            reviewed_apply_plan_artifact_path=args.reviewed_apply_plan_artifact,
            reviewed_teardown_plan_artifact_path=args.reviewed_teardown_plan_artifact,
            reviewed_cost_cutoff_apply_plan_artifact_path=args.reviewed_cost_cutoff_apply_plan_artifact,
            reviewed_cost_cutoff_destroy_plan_artifact_path=args.reviewed_cost_cutoff_destroy_plan_artifact,
        )
    except (P176LiveCampaignError, P176LiveBridgeError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "phase": "p176",
                    "status": "blocked",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    print(json.dumps({"phase": "p176", **result}, sort_keys=True))
    return 0


def orchestrate_live_campaign(
    *,
    run_dir: str | Path,
    state_path: str | Path | None = None,
    mode: str = "fresh-lab",
    reviewed_apply_plan_artifact_path: str | Path | None = None,
    reviewed_teardown_plan_artifact_path: str | Path | None = None,
    reviewed_cost_cutoff_apply_plan_artifact_path: str | Path | None = None,
    reviewed_cost_cutoff_destroy_plan_artifact_path: str | Path | None = None,
) -> dict[str, Any]:
    campaign_mode = resolve_campaign_mode(mode)
    directory = Path(run_dir)
    if not directory.is_dir() or directory.is_symlink():
        raise P176LiveCampaignError(f"run_dir_missing_or_unsafe:{directory}")
    state_file = Path(state_path) if state_path is not None else directory / "live-campaign-state.json"
    if state_file.is_symlink():
        raise P176LiveCampaignError(f"state_path_unsafe:{state_file}")

    campaign = generate_p176_campaign()
    input_manifest = _validate_frozen_input_manifest(campaign)
    input_manifest_hash = file_hash(INPUT_MANIFEST_PATH)
    _ensure_run_input_manifest(directory, expected_hash=input_manifest_hash)
    existing_state = _load_state(state_file)
    if existing_state is not None:
        _validate_resume_state(existing_state, campaign_hash=str(campaign["campaign_hash"]), input_manifest_hash=input_manifest_hash)
    adoption_binding = _load_adoption_baseline_binding(directory) if campaign_mode == "p174-workload-adoption" else None

    missing = _missing_observation_paths(directory)
    run_id = _state_run_id(existing_state) or _adoption_run_id(adoption_binding) or _read_project_run_id(directory) or _deterministic_run_id(directory)
    if missing:
        readiness = _build_readiness(
            run_id=run_id,
            campaign=campaign,
            input_manifest=input_manifest,
            input_manifest_hash=input_manifest_hash,
            missing_observation_artifacts=missing,
        )
        write_json(directory / "live-campaign-readiness.json", readiness)
        state = _build_state(
            run_id=run_id,
            status="readiness_only",
            campaign_hash=str(campaign["campaign_hash"]),
            input_manifest_hash=input_manifest_hash,
            completed_steps=["frozen_inputs_validated", "readiness_artifact_emitted"],
            readiness_hash=str(readiness["readiness_hash"]),
        )
        write_json(state_file, state)
        return {
            "mode": campaign_mode,
            "result_mode": "readiness",
            "status": "readiness_only",
            "run_id": run_id,
            "readiness_hash": readiness["readiness_hash"],
            "missing_observation_artifacts": missing,
        }

    reviewed_plan_artifacts = _reviewed_plan_artifacts(
        directory,
        existing_state=existing_state,
        reviewed_apply_plan_artifact_path=reviewed_apply_plan_artifact_path,
        reviewed_teardown_plan_artifact_path=reviewed_teardown_plan_artifact_path,
        reviewed_cost_cutoff_apply_plan_artifact_path=reviewed_cost_cutoff_apply_plan_artifact_path,
        reviewed_cost_cutoff_destroy_plan_artifact_path=reviewed_cost_cutoff_destroy_plan_artifact_path,
    )
    bridge_result = materialize_live_release_inputs(
        directory,
        reviewed_apply_plan_artifact_path=reviewed_plan_artifacts["reviewed_apply_plan_artifact_path"],
        reviewed_teardown_plan_artifact_path=reviewed_plan_artifacts["reviewed_teardown_plan_artifact_path"],
        reviewed_cost_cutoff_apply_plan_artifact_path=reviewed_plan_artifacts[
            "reviewed_cost_cutoff_apply_plan_artifact_path"
        ],
        reviewed_cost_cutoff_destroy_plan_artifact_path=reviewed_plan_artifacts[
            "reviewed_cost_cutoff_destroy_plan_artifact_path"
        ],
    )
    state = _build_state(
        run_id=bridge_result.run_id,
        status=bridge_result.subordinate_status,
        campaign_hash=str(campaign["campaign_hash"]),
        input_manifest_hash=input_manifest_hash,
        completed_steps=[
            "frozen_inputs_validated",
            "observed_artifacts_validated",
            "strata_reconciliation_validated",
            "release_inputs_materialized",
        ],
        release_inputs_manifest_hash=bridge_result.release_inputs_manifest_hash,
        live_artifact_manifest_hash=bridge_result.live_artifact_manifest_hash,
        reviewed_plan_artifacts=_relative_plan_artifacts(directory, reviewed_plan_artifacts),
    )
    write_json(state_file, state)
    return {"status": bridge_result.subordinate_status, **bridge_result.as_dict()}


def resolve_campaign_mode(mode: str) -> str:
    if mode not in CAMPAIGN_MODES:
        raise P176LiveCampaignError("campaign_mode_invalid")
    return mode


def _load_adoption_baseline_binding(directory: Path) -> dict[str, Any]:
    path = directory / ADOPTION_BASELINE_BINDING_PATH
    if not path.is_file() or path.is_symlink():
        raise P176LiveCampaignError("adoption_baseline_binding_required")
    try:
        return validate_adoption_baseline_binding(load_json(path))
    except (P176LiveGateError, P176LiveBridgeError) as exc:
        raise P176LiveCampaignError(f"adoption_baseline_binding_invalid:{exc}") from exc


def _adoption_run_id(binding: Mapping[str, Any] | None) -> str | None:
    if binding is None:
        return None
    run_id = binding.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise P176LiveCampaignError("adoption_baseline_run_id_invalid")
    return run_id


def _validate_frozen_input_manifest(campaign: Mapping[str, Any]) -> dict[str, Any]:
    value = _mapping(load_json(INPUT_MANIFEST_PATH), "input_manifest")
    required = {
        "schema_version",
        "campaign_hash",
        "campaign_id",
        "episode_count",
        "generator",
        "healthy_noisy_window_count",
        "sealed_truth_file_hash",
        "sealed_truth_hash",
        "sealed_truth_path",
        "seed",
        "truth_payload_policy",
    }
    if set(value) != required or value.get("schema_version") != "p176.input_manifest.v1":
        raise P176LiveCampaignError("input_manifest_keyset_invalid")
    if value.get("campaign_hash") != campaign.get("campaign_hash"):
        raise P176LiveCampaignError("input_manifest_campaign_hash_mismatch")
    if value.get("campaign_id") != campaign.get("campaign_id") or value.get("seed") != campaign.get("seed"):
        raise P176LiveCampaignError("input_manifest_campaign_identity_mismatch")
    if value.get("episode_count") != 480 or value.get("healthy_noisy_window_count") != 240:
        raise P176LiveCampaignError("input_manifest_denominator_mismatch")
    if len(campaign["episodes"]) != 480 or len(campaign["healthy_windows"]) != 240:
        raise P176LiveCampaignError("campaign_denominator_mismatch")
    return dict(value)


def _ensure_run_input_manifest(directory: Path, *, expected_hash: str) -> None:
    target = directory / "input-manifest.json"
    if target.is_symlink():
        raise P176LiveCampaignError("run_input_manifest_unsafe")
    if target.exists():
        if file_hash(target) != expected_hash:
            raise P176LiveCampaignError("run_input_manifest_hash_mismatch")
        return
    target.write_bytes(INPUT_MANIFEST_PATH.read_bytes())
    if file_hash(target) != expected_hash:
        raise P176LiveCampaignError("run_input_manifest_hash_mismatch")


def _load_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    value = _mapping(load_json(path), "state")
    if set(value) - {
        "schema_version",
        "phase",
        "run_id",
        "campaign_hash",
        "input_manifest_hash",
        "status",
        "completed_steps",
        "readiness_hash",
        "release_inputs_manifest_hash",
        "live_artifact_manifest_hash",
        "reviewed_plan_artifacts",
        "state_hash",
    }:
        raise P176LiveCampaignError("state_keyset_invalid")
    if value.get("schema_version") != STATE_SCHEMA_VERSION or value.get("phase") != "p176":
        raise P176LiveCampaignError("state_schema_invalid")
    if value.get("state_hash") != stable_hash({key: item for key, item in value.items() if key != "state_hash"}):
        raise P176LiveCampaignError("state_hash_invalid")
    return dict(value)


def _validate_resume_state(state: Mapping[str, Any], *, campaign_hash: str, input_manifest_hash: str) -> None:
    if state.get("campaign_hash") != campaign_hash:
        raise P176LiveCampaignError("state_campaign_hash_mismatch")
    if state.get("input_manifest_hash") != input_manifest_hash:
        raise P176LiveCampaignError("state_input_manifest_hash_mismatch")
    if not isinstance(state.get("completed_steps"), list) or any(not isinstance(item, str) for item in state["completed_steps"]):
        raise P176LiveCampaignError("state_completed_steps_invalid")
    if "reviewed_plan_artifacts" in state:
        _validate_persisted_plan_artifacts(state["reviewed_plan_artifacts"])


def _missing_observation_paths(directory: Path) -> list[str]:
    return [
        path
        for path in (EPISODE_OBSERVATIONS_PATH, HEALTHY_WINDOW_OBSERVATIONS_PATH)
        if not (directory / path).is_file() or (directory / path).is_symlink()
    ]


def _build_readiness(
    *,
    run_id: str,
    campaign: Mapping[str, Any],
    input_manifest: Mapping[str, Any],
    input_manifest_hash: str,
    missing_observation_artifacts: list[str],
) -> dict[str, Any]:
    readiness: dict[str, Any] = {
        "schema_version": READINESS_SCHEMA_VERSION,
        "phase": "p176",
        "run_id": run_id,
        "status": READINESS_STATUS,
        "qualified": False,
        "qualification_artifacts_emitted": False,
        "reason": "observed_results_not_supplied",
        "campaign_hash": campaign["campaign_hash"],
        "input_manifest_hash": input_manifest_hash,
        "campaign_id": input_manifest["campaign_id"],
        "seed": input_manifest["seed"],
        "expected_episode_count": 480,
        "expected_healthy_window_count": 240,
        "observed_episode_count": 0,
        "observed_healthy_window_count": 0,
        "missing_observation_artifacts": list(missing_observation_artifacts),
        "build_release_artifacts_target": "app.services.p176_release.build_release_artifacts",
        "cloud_apply_performed": False,
        "fault_mutation_performed": False,
        "fabricated_outcome_count": 0,
        "readiness_hash": "",
    }
    readiness["readiness_hash"] = stable_hash({key: value for key, value in readiness.items() if key != "readiness_hash"})
    return readiness


def _build_state(
    *,
    run_id: str,
    status: str,
    campaign_hash: str,
    input_manifest_hash: str,
    completed_steps: list[str],
    readiness_hash: str | None = None,
    release_inputs_manifest_hash: str | None = None,
    live_artifact_manifest_hash: str | None = None,
    reviewed_plan_artifacts: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "schema_version": STATE_SCHEMA_VERSION,
        "phase": "p176",
        "run_id": run_id,
        "campaign_hash": campaign_hash,
        "input_manifest_hash": input_manifest_hash,
        "status": status,
        "completed_steps": completed_steps,
    }
    if readiness_hash is not None:
        state["readiness_hash"] = readiness_hash
    if release_inputs_manifest_hash is not None:
        state["release_inputs_manifest_hash"] = release_inputs_manifest_hash
    if live_artifact_manifest_hash is not None:
        state["live_artifact_manifest_hash"] = live_artifact_manifest_hash
    if reviewed_plan_artifacts is not None:
        state["reviewed_plan_artifacts"] = dict(reviewed_plan_artifacts)
    state["state_hash"] = stable_hash(state)
    return state


def _reviewed_plan_artifacts(
    directory: Path,
    *,
    existing_state: Mapping[str, Any] | None,
    reviewed_apply_plan_artifact_path: str | Path | None,
    reviewed_teardown_plan_artifact_path: str | Path | None,
    reviewed_cost_cutoff_apply_plan_artifact_path: str | Path | None,
    reviewed_cost_cutoff_destroy_plan_artifact_path: str | Path | None,
) -> dict[str, Path]:
    supplied = {
        "reviewed_apply_plan_artifact_path": reviewed_apply_plan_artifact_path,
        "reviewed_teardown_plan_artifact_path": reviewed_teardown_plan_artifact_path,
        "reviewed_cost_cutoff_apply_plan_artifact_path": reviewed_cost_cutoff_apply_plan_artifact_path,
        "reviewed_cost_cutoff_destroy_plan_artifact_path": reviewed_cost_cutoff_destroy_plan_artifact_path,
    }
    if any(path is not None for path in supplied.values()):
        if any(path is None for path in supplied.values()):
            raise P176LiveCampaignError("reviewed_plan_artifact_paths_incomplete")
        return {
            field: _validated_reviewed_plan_artifact(directory, Path(path), field=field)
            for field, path in supplied.items()
            if path is not None
        }

    if existing_state is None or "reviewed_plan_artifacts" not in existing_state:
        raise P176LiveCampaignError("reviewed_plan_artifact_paths_required")
    persisted = _validate_persisted_plan_artifacts(existing_state["reviewed_plan_artifacts"])
    return {
        field: _validated_reviewed_plan_artifact(directory, directory / relative_path, field=field)
        for field, relative_path in persisted.items()
    }


def _validate_persisted_plan_artifacts(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != REVIEWED_PLAN_ARTIFACT_FIELDS:
        raise P176LiveCampaignError("reviewed_plan_artifacts_state_invalid")
    result: dict[str, str] = {}
    for field, raw_path in value.items():
        if not isinstance(raw_path, str) or not raw_path or Path(raw_path).is_absolute() or ".." in Path(raw_path).parts:
            raise P176LiveCampaignError(f"{field}_state_path_invalid")
        result[str(field)] = raw_path
    return result


def _validated_reviewed_plan_artifact(directory: Path, path: Path, *, field: str) -> Path:
    if path.is_symlink():
        raise P176LiveCampaignError(f"{field}_symlink")
    if not path.is_file():
        raise P176LiveCampaignError(f"{field}_missing")
    root = directory.resolve(strict=True)
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise P176LiveCampaignError(f"{field}_outside_run_evidence_root") from exc
    return resolved


def _relative_plan_artifacts(directory: Path, artifacts: Mapping[str, Path]) -> dict[str, str]:
    root = directory.resolve(strict=True)
    return {field: artifact.relative_to(root).as_posix() for field, artifact in artifacts.items()}


def _read_project_run_id(directory: Path) -> str | None:
    binding = directory / "project-binding.json"
    if not binding.is_file() or binding.is_symlink():
        return None
    value = _mapping(load_json(binding), "project_binding")
    run_id = value.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise P176LiveCampaignError("project_binding_run_id_invalid")
    return run_id


def _state_run_id(state: Mapping[str, Any] | None) -> str | None:
    if state is None:
        return None
    run_id = state.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise P176LiveCampaignError("state_run_id_invalid")
    return run_id


def _deterministic_run_id(directory: Path) -> str:
    digest = stable_hash(str(directory.resolve())).split(":", 1)[1][:16]
    return f"p176-live-{digest}"


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P176LiveCampaignError(f"{field}_must_be_object")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
