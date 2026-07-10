"""Closed P106 preventive capability registry and compiler."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.models.action import ActionMetadata, ActionRequest
from app.services.failure_forecast_engine import G006_ZERO_AUTHORITY
from app.services.policy_engine import PolicyContext, PolicyEngine, default_capabilities
from app.services.risk_engine import DEFAULT_ACTION_REGISTRY, PROHIBITED_ACTIONS, RiskEngine

PROHIBITED_CAPABILITY_ACTIONS = set(PROHIBITED_ACTIONS) | {
    "production.rollback",
    "production.restart_service",
    "database.mutate",
    "shell.execute",
    "cloud.delete_resource",
    "secret.read",
}


@dataclass(frozen=True)
class PreventiveCapability:
    capability_id: str
    family: str
    action_type: str
    environment_allowlist: tuple[str, ...]
    required_evidence: tuple[str, ...]
    preconditions: tuple[str, ...]
    post_checks: tuple[str, ...]
    canary_scope_template: Mapping[str, Any] | None
    rollback_trigger: str | None
    reversible: bool
    intervention_cost: float
    mutation_shaped: bool


@dataclass(frozen=True)
class CompiledPreventiveCapability:
    capability: PreventiveCapability
    action_request: ActionRequest
    policy_context: PolicyContext
    execution_enabled: bool = False
    simulation_only: bool = True
    p107_required_for_execution: bool = True


@dataclass(frozen=True)
class PreventiveCapabilityComposition:
    capabilities: Mapping[str, PreventiveCapability]
    registry_hash: str
    registry_hashes: Mapping[str, str]
    registry_parity_hashes: Mapping[str, str]
    registry_hash_parity: bool
    registry_hash_mismatch_exposed: bool
    risk_engine: RiskEngine
    policy_engine: PolicyEngine
    authority: Mapping[str, Any]

    def compile_capability(
        self,
        capability_id: str,
        *,
        service: str,
        environment: str,
        evidence_ids: list[str] | tuple[str, ...],
        tenant_id: str = "demo",
        workspace_id: str = "demo",
        payload: Mapping[str, Any] | None = None,
    ) -> CompiledPreventiveCapability:
        capability = self.capabilities.get(capability_id)
        if capability is None:
            raise ValueError(f"unknown capability {capability_id}")
        if environment not in capability.environment_allowlist:
            raise ValueError(f"environment {environment} is not allowed for {capability_id}")
        merged_payload = {
            "capability_id": capability.capability_id,
            "family": capability.family,
            "evidence_ids": list(evidence_ids),
            "required_evidence": list(capability.required_evidence),
            "preconditions": list(capability.preconditions),
            "post_checks": list(capability.post_checks),
            "canary_scope_template": capability.canary_scope_template,
            "rollback_trigger": capability.rollback_trigger,
            **dict(payload or {}),
        }
        request = ActionRequest(
            action_type=capability.action_type,
            target=service,
            environment=environment,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            payload=merged_payload,
        )
        action = self.risk_engine.get_action(capability.action_type)
        context = PolicyContext(
            capabilities=default_capabilities(action.required_capabilities if action else ()),
            service=service,
            environment=environment,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            evidence_count=len(evidence_ids),
            reversible=capability.reversible,
        )
        return CompiledPreventiveCapability(capability=capability, action_request=request, policy_context=context)


def load_preventive_capability_registry(path: str | Path) -> PreventiveCapabilityComposition:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != "p106.capability_registry.v1":
        raise ValueError("unsupported p106 capability registry schema")
    authority = data.get("authority")
    if authority != G006_ZERO_AUTHORITY:
        raise ValueError("registry authority must exactly equal zero authority")
    capabilities = _load_capabilities(data)
    registry = dict(DEFAULT_ACTION_REGISTRY)
    _validate_action_coverage(capabilities, registry)
    risk_engine = RiskEngine(registry)
    policy_engine = PolicyEngine(risk_engine)
    registry_hashes = {
        "fixture": _canonical_hash(data),
        "capability_registry": _capability_hash(capabilities, registry),
        "shared_risk_engine": _registry_projection_hash(risk_engine.registry),
        "policy_engine": _registry_projection_hash(policy_engine.risk_engine.registry),
        "blast_radius_service": _registry_projection_hash(policy_engine.blast_radius_service.risk_engine.registry),
        "action_simulator": _registry_projection_hash(policy_engine.action_simulator.risk_engine.registry),
    }
    if not (policy_engine.risk_engine is risk_engine and policy_engine.blast_radius_service.risk_engine is risk_engine and policy_engine.action_simulator.risk_engine is risk_engine):
        raise AssertionError("preventive registry composition must share one RiskEngine instance")
    registry_parity_hashes = {
        "fixture": _fixture_parity_hash(data, registry),
        "capability_registry": _capability_hash(capabilities, registry),
        "shared_risk_engine": _service_parity_hash(capabilities, risk_engine.registry),
        "policy_engine": _service_parity_hash(capabilities, policy_engine.risk_engine.registry),
        "blast_radius_service": _service_parity_hash(
            capabilities,
            policy_engine.blast_radius_service.risk_engine.registry,
        ),
        "action_simulator": _service_parity_hash(capabilities, policy_engine.action_simulator.risk_engine.registry),
    }
    parity_values = set(registry_parity_hashes.values())
    registry_hash_parity = len(parity_values) == 1
    if not registry_hash_parity:
        raise AssertionError(f"preventive registry canonical hash parity failed: {registry_parity_hashes}")
    parity_hash = registry_parity_hashes["capability_registry"]
    return PreventiveCapabilityComposition(
        capabilities=capabilities,
        registry_hash=parity_hash,
        registry_hashes=registry_hashes,
        registry_parity_hashes=registry_parity_hashes,
        registry_hash_parity=registry_hash_parity,
        registry_hash_mismatch_exposed=len(set(registry_hashes.values())) != 1,
        risk_engine=risk_engine,
        policy_engine=policy_engine,
        authority=authority,
    )


def compile_preventive_capability(
    capability_id: str,
    *,
    service: str,
    environment: str,
    evidence_ids: list[str] | tuple[str, ...],
    registry_path: str | Path = "evals/prevention/p106_capability_registry.json",
) -> CompiledPreventiveCapability:
    return load_preventive_capability_registry(registry_path).compile_capability(
        capability_id,
        service=service,
        environment=environment,
        evidence_ids=evidence_ids,
    )


def _load_capabilities(data: Mapping[str, Any]) -> dict[str, PreventiveCapability]:
    raw_capabilities = data.get("capabilities")
    if not isinstance(raw_capabilities, list) or not raw_capabilities:
        raise ValueError("capabilities must be a non-empty list")
    capabilities: dict[str, PreventiveCapability] = {}
    for raw in raw_capabilities:
        if not isinstance(raw, Mapping):
            raise ValueError("capability entry must be a mapping")
        capability = PreventiveCapability(
            capability_id=str(raw.get("capability_id", "")),
            family=str(raw.get("family", "")),
            action_type=str(raw.get("action_type", "")),
            environment_allowlist=tuple(str(item) for item in raw.get("environment_allowlist", ())),
            required_evidence=tuple(str(item) for item in raw.get("required_evidence", ())),
            preconditions=tuple(str(item) for item in raw.get("preconditions", ())),
            post_checks=tuple(str(item) for item in raw.get("post_checks", ())),
            canary_scope_template=raw.get("canary_scope_template") if isinstance(raw.get("canary_scope_template"), Mapping) else None,
            rollback_trigger=str(raw["rollback_trigger"]) if raw.get("rollback_trigger") is not None else None,
            reversible=raw.get("reversible") is True,
            intervention_cost=float(raw.get("intervention_cost", 0.0)),
            mutation_shaped=raw.get("mutation_shaped") is True,
        )
        _validate_capability(capability)
        if capability.capability_id in capabilities:
            raise ValueError(f"duplicate capability id {capability.capability_id}")
        capabilities[capability.capability_id] = capability
    return capabilities


def _validate_capability(capability: PreventiveCapability) -> None:
    if not capability.capability_id:
        raise ValueError("capability id is required")
    if capability.action_type in PROHIBITED_CAPABILITY_ACTIONS:
        raise ValueError(f"{capability.action_type} is prohibited for preventive registry")
    if any(token in capability.action_type for token in ("shell", "secret", "database", "cloud", "production")):
        raise ValueError(f"{capability.action_type} uses prohibited action family")
    if "production" in capability.environment_allowlist or not capability.environment_allowlist:
        raise ValueError("production environments are not allowed")
    if not capability.required_evidence:
        raise ValueError("required evidence is mandatory")
    if capability.mutation_shaped:
        if not capability.rollback_trigger:
            raise ValueError("mutation-shaped capabilities require rollback trigger")
        if not capability.post_checks:
            raise ValueError("mutation-shaped capabilities require post-checks")
        if not capability.canary_scope_template:
            raise ValueError("mutation-shaped capabilities require canary scope")
        if capability.reversible is not True:
            raise ValueError("mutation-shaped capabilities must be reversible")


def _validate_action_coverage(capabilities: Mapping[str, PreventiveCapability], registry: Mapping[str, ActionMetadata]) -> None:
    for capability in capabilities.values():
        action = registry.get(capability.action_type)
        if action is None:
            raise ValueError(f"unresolved action type {capability.action_type}")
        if action.name != capability.action_type:
            raise ValueError(f"metadata mismatch for {capability.action_type}")
        if capability.mutation_shaped and (not action.reversible or not action.post_checks):
            raise ValueError(f"incomplete ActionMetadata for {capability.action_type}")


def _canonical_hash(data: Any) -> str:
    normalized = json.loads(json.dumps(data, sort_keys=True, default=str))
    normalized.pop("fixture_sha256", None) if isinstance(normalized, dict) else None
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _capability_hash(capabilities: Mapping[str, PreventiveCapability], registry: Mapping[str, ActionMetadata]) -> str:
    return _canonical_hash(_capability_projection(capabilities, registry))


def _fixture_parity_hash(data: Mapping[str, Any], registry: Mapping[str, ActionMetadata]) -> str:
    raw_capabilities = data.get("capabilities", ())
    if not isinstance(raw_capabilities, list):
        raise ValueError("capabilities must be a list for parity hashing")
    capabilities: dict[str, dict[str, Any]] = {}
    action_types: list[str] = []
    for raw in raw_capabilities:
        if not isinstance(raw, Mapping):
            raise ValueError("capability entry must be a mapping for parity hashing")
        capability_id = str(raw.get("capability_id", ""))
        action_type = str(raw.get("action_type", ""))
        capabilities[capability_id] = _raw_capability_projection(raw)
        action_types.append(action_type)
    return _canonical_hash(_canonical_projection(capabilities, action_types, registry))


def _service_parity_hash(
    capabilities: Mapping[str, PreventiveCapability],
    registry: Mapping[str, ActionMetadata],
) -> str:
    return _canonical_hash(_capability_projection(capabilities, registry))


def _capability_projection(
    capabilities: Mapping[str, PreventiveCapability],
    registry: Mapping[str, ActionMetadata],
) -> dict[str, Any]:
    projected_capabilities = {key: asdict(value) for key, value in sorted(capabilities.items())}
    action_types = [capability.action_type for capability in capabilities.values()]
    return _canonical_projection(projected_capabilities, action_types, registry)


def _canonical_projection(
    capabilities: Mapping[str, Mapping[str, Any]],
    action_types: list[str],
    registry: Mapping[str, ActionMetadata],
) -> dict[str, Any]:
    return {
        "capabilities": dict(capabilities),
        "actions": {action_type: _metadata_projection(registry[action_type]) for action_type in action_types},
    }


def _raw_capability_projection(raw: Mapping[str, Any]) -> dict[str, Any]:
    canary_scope = raw.get("canary_scope_template")
    return {
        "capability_id": str(raw.get("capability_id", "")),
        "family": str(raw.get("family", "")),
        "action_type": str(raw.get("action_type", "")),
        "environment_allowlist": tuple(str(item) for item in raw.get("environment_allowlist", ())),
        "required_evidence": tuple(str(item) for item in raw.get("required_evidence", ())),
        "preconditions": tuple(str(item) for item in raw.get("preconditions", ())),
        "post_checks": tuple(str(item) for item in raw.get("post_checks", ())),
        "canary_scope_template": canary_scope if isinstance(canary_scope, Mapping) else None,
        "rollback_trigger": str(raw["rollback_trigger"]) if raw.get("rollback_trigger") is not None else None,
        "reversible": raw.get("reversible") is True,
        "intervention_cost": float(raw.get("intervention_cost", 0.0)),
        "mutation_shaped": raw.get("mutation_shaped") is True,
    }


def _registry_projection_hash(registry: Mapping[str, ActionMetadata]) -> str:
    return _canonical_hash({key: _metadata_projection(value) for key, value in sorted(registry.items())})


def _metadata_projection(metadata: ActionMetadata) -> dict[str, Any]:
    projected = asdict(metadata)
    projected["base_risk"] = str(metadata.base_risk)
    return projected
