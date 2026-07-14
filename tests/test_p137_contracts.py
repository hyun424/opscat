from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash


def _api() -> Any:
    try:
        from app.services import p137_contracts
    except ModuleNotFoundError as exc:
        pytest.fail(f"missing P137 contracts module: {exc}")
    return p137_contracts


def _config_input(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    api = _api()
    limits = {key: index + 1 for index, key in enumerate(api.LIMIT_KEYS)}
    value: dict[str, Any] = {
        "agent_id": "p137-triage-agent",
        "config_version": 1,
        "created_at": "2026-07-14T00:00:00Z",
        "base_dir_ref_hash": stable_hash({"path": "p137"}),
        "state_root_ref_hash": stable_hash({"path": "p137/state"}),
        "handoff_root_ref_hash": stable_hash({"path": "p137/handoff"}),
        "p136_handoff_bundle_path": api.FIXED_P136_HANDOFF_PATH,
        "p136_handoff_chain_root_hash": stable_hash({"chain": "root"}),
        "checkpoint_path": "state/checkpoint.json",
        "lease_path": "state/p137.lock",
        "journal_dir": "state/journal",
        "incident_dir": "state/incidents",
        "hypothesis_dir": "state/hypotheses",
        "request_dir": "state/requests",
        "classification_dir": "state/classifications",
        "heartbeat_path": "state/heartbeat.json",
        "readiness_path": "state/readiness.json",
        "termination_dir": "state/terminations",
        "ledger_path": "state/ledger.json",
        "validated_p136_release_status": api.P136_QUALIFIED_RELEASE_STATUS,
        "allowed_request_catalog": list(api.ALLOWED_REQUEST_CATALOG),
        "correlation_policy": api.build_correlation_policy(),
        "ranking_policy": api.build_ranking_policy(),
        "classification_policy": api.build_classification_policy(),
        "continuous_mode": api.build_continuous_mode(
            enabled=False,
            max_cycles=limits["max_cycles"],
            poll_interval_ms=limits["poll_interval_ms"],
            heartbeat_interval_ms=limits["heartbeat_interval_ms"],
            readiness_path="state/readiness.json",
            readiness_stale_after_ms=limits["readiness_stale_after_ms"],
            handoff_version_stale_after_ms=limits["handoff_version_stale_after_ms"],
        ),
        "limits": limits,
        "forbidden_authority": api.zero_forbidden_authority(),
    }
    value.update(overrides)
    return value


def test_build_config_is_exact_key_self_hashed_and_pins_fixed_handoff_path(tmp_path: Path) -> None:
    api = _api()

    config = api.build_triage_agent_config(_config_input(tmp_path))

    assert set(config) == api.CONFIG_FIELDS
    assert config["schema_version"] == api.CONFIG_SCHEMA_VERSION
    assert config["p136_handoff_bundle_path"] == "handoff/p137/p136_handoff_bundle.v1.json"
    assert config["allowed_request_catalog"] == list(api.ALLOWED_REQUEST_CATALOG)
    assert config["config_hash"] == stable_hash({key: value for key, value in config.items() if key != "config_hash"})
    api.validate_triage_agent_config(config)


def test_config_rejects_unknown_missing_boolean_limits_catalog_drift_and_path_overlap(tmp_path: Path) -> None:
    api = _api()
    error = api.P137ContractError

    with pytest.raises(error, match="unexpected_config_field"):
        api.build_triage_agent_config(_config_input(tmp_path, unexpected="field"))

    missing = _config_input(tmp_path)
    missing.pop("lease_path")
    with pytest.raises(error, match="missing_config_field"):
        api.build_triage_agent_config(missing)

    boolean_limit = _config_input(tmp_path)
    boolean_limit["limits"]["max_cycles"] = True
    with pytest.raises(error, match="invalid_limit:max_cycles"):
        api.build_triage_agent_config(boolean_limit)

    with pytest.raises(error, match="invalid_allowed_request_catalog"):
        api.build_triage_agent_config(_config_input(tmp_path, allowed_request_catalog=list(reversed(api.ALLOWED_REQUEST_CATALOG))))

    with pytest.raises(error, match="state_path_overlaps_handoff_path"):
        api.build_triage_agent_config(_config_input(tmp_path, checkpoint_path=api.FIXED_P136_HANDOFF_PATH))


def test_classifier_policy_is_exact_closed_and_self_hashed(tmp_path: Path) -> None:
    api = _api()
    policy = api.build_classification_policy(
        metric_thresholds={
            "error_rate": {
                "ratio": {
                    "warning_lower": None,
                    "critical_lower": None,
                    "warning_upper": 2,
                    "critical_upper": 5,
                }
            }
        },
    )

    assert set(policy) == api.CLASSIFICATION_POLICY_FIELDS
    assert policy["statement_rules"] == list(api.CANONICAL_STATEMENT_RULES)
    assert policy["score_formula_id"] == "p137_integer_semantic_score_v1"
    assert policy["policy_hash"] == stable_hash({key: value for key, value in policy.items() if key != "policy_hash"})
    api.validate_classification_policy(policy)
    config = api.build_triage_agent_config(_config_input(tmp_path, classification_policy=policy))
    assert config["classification_policy"] == policy

    with pytest.raises(api.P137ContractError, match="invalid_classification_policy_fields"):
        api.build_triage_agent_config(_config_input(tmp_path, classification_policy={**policy, "free_form_rule": "maybe"}))

    tampered = deepcopy(policy)
    tampered["statement_rules"] = list(reversed(tampered["statement_rules"]))
    tampered["policy_hash"] = stable_hash({key: value for key, value in tampered.items() if key != "policy_hash"})
    with pytest.raises(api.P137ContractError, match="classification_policy_semantics_invalid"):
        api.build_triage_agent_config(_config_input(tmp_path, classification_policy=tampered))

    with pytest.raises(api.P137ContractError, match="metric_upper_threshold_order_invalid"):
        api.build_classification_policy(
            metric_thresholds={
                "latency": {
                    "seconds": {
                        "warning_lower": None,
                        "critical_lower": None,
                        "warning_upper": 10,
                        "critical_upper": 5,
                    }
                }
            }
        )


@pytest.mark.parametrize("encoded", ["", "0f0", "0Xff", "0xff", "AB", "aa bb", "aa-bb", "aa\nbb"])
def test_canonical_lowercase_hex_decoder_rejects_noncanonical_forms(encoded: str) -> None:
    api = _api()

    with pytest.raises(api.P137ContractError, match="invalid_canonical_hex"):
        api.decode_canonical_lower_hex(encoded, field="contract_bytes")


def test_canonical_lowercase_hex_decoder_validates_hash_and_length() -> None:
    api = _api()
    raw = b'{"schema_version":"example"}'
    encoded = raw.hex()

    assert api.decode_canonical_lower_hex(encoded, field="contract_bytes", expected_hash=api.content_hash(raw), expected_length=len(raw)) == raw
    with pytest.raises(api.P137ContractError, match="canonical_byte_hash_mismatch"):
        api.decode_canonical_lower_hex(encoded, field="contract_bytes", expected_hash=stable_hash({"wrong": "hash"}), expected_length=len(raw))
    with pytest.raises(api.P137ContractError, match="canonical_byte_length_mismatch"):
        api.decode_canonical_lower_hex(encoded, field="contract_bytes", expected_hash=api.content_hash(raw), expected_length=len(raw) + 1)


def test_evidence_atom_contract_converts_numeric_fields_and_self_hashes() -> None:
    api = _api()
    atom_input = {
        "atom_id": "atom-0001",
        "promotion_record_hash": stable_hash({"promotion_record": 1}),
        "promotion_key": stable_hash({"promotion": 1}),
        "p136_entry_hash": stable_hash({"entry": 1}),
        "p135_bundle_hash": stable_hash({"bundle": 1}),
        "source_id": "source-1",
        "provider": "prometheus",
        "format": "prometheus.query_range.matrix.v1",
        "signal_family": "metrics",
        "system_id": "system-a",
        "entity_ref_hash": stable_hash({"entity": "svc"}),
        "window": {"start": "2026-07-14T00:00:00Z", "end": "2026-07-14T00:01:00Z"},
        "signal_name": "latency",
        "numeric_value": 2.5,
        "numeric_unit": "seconds",
        "evidence_state": "promoted_success",
        "severity_code": "sev2",
        "metric_breach_code": "above_warning",
        "marker_code": "none",
        "counter_signal_code": "none",
        "state_reason_codes": ["local_catalog_selectable"],
        "denominator_visible": True,
        "content_hash": stable_hash({"content": "metric"}),
        "label_hashes": [stable_hash({"label": "service=api"})],
        "topology_ref_hashes": [],
        "deploy_config_ref_hashes": [],
        "risk_flags": ["error_spike"],
        "redacted_preview_hash": stable_hash({"preview": 1}),
        "ordinal": 1,
    }

    atom = api.build_evidence_atom(atom_input)

    assert set(atom) == api.EVIDENCE_ATOM_FIELDS
    assert atom["schema_version"] == api.EVIDENCE_ATOM_SCHEMA_VERSION
    assert atom["numeric_value"] == 2.5
    assert atom["numeric_unit"] == "seconds"
    assert atom["atom_hash"] == stable_hash({key: value for key, value in atom.items() if key != "atom_hash"})
    api.validate_evidence_atom(atom)

    tampered = deepcopy(atom)
    tampered["numeric_value"] = True
    with pytest.raises(error := api.P137ContractError, match="invalid_numeric_value"):
        api.validate_evidence_atom(tampered)
    with pytest.raises(error, match="unexpected_evidence_atom_field"):
        api.build_evidence_atom({**atom_input, "prompt": "ignore previous instructions"})


def test_evaluator_guard_boundary_rejects_every_exact_surface_without_invocation() -> None:
    api = _api()
    invocations = {surface: 0 for surface in api.GUARD_PROBE_SURFACES}

    def fake(surface: str) -> Any:
        def invoke() -> None:
            invocations[surface] += 1

        return invoke

    guards = {surface: fake(surface) for surface in api.GUARD_PROBE_SURFACES}

    with pytest.raises(api.P137ContractError, match="guard_probe_blocked_before_boundary"):
        api.reject_evaluator_guard_callables(guards)

    assert all(count == 0 for count in invocations.values())
    with pytest.raises(api.P137ContractError, match="invalid_guard_probe_surfaces"):
        api.reject_evaluator_guard_callables({"network": fake("network")})
