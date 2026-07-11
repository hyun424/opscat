"""P106 simulation-only preventive action planner.

The planner validates the canonical P105 artifact, composes capabilities through
the shared preventive registry, and produces P107 handoff plans. It has no
execution authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from importlib import import_module
from pathlib import Path
from typing import Any

from app.models.action import ActionRequest, PolicyDecision
from app.services.incident_memory import IncidentMemory, failed_remediation_warning, summarize_matches
from app.services.policy_engine import PolicyContext

_IMMUTABLE_BOUNDARY = {
    "execution_enabled": False,
    "simulation_only": True,
    "p107_required_for_execution": True,
}

_CAPABILITY_REGISTRY_PATH = Path("evals/prevention/p106_capability_registry.json")
_SUPPORTED_FAMILIES = frozenset({"deploy", "queue", "database"})
_MIN_PROBABILITY = 0.55
_SAFETY_CONFIDENCE_THRESHOLD = 0.80


class PreventiveActionPlanner:
    """Compile and rank preventive candidates behind mandatory safety gates."""

    def __init__(
        self,
        *,
        incident_memory: IncidentMemory | None = None,
        p105_prerequisite: Any | None = None,
    ) -> None:
        self.incident_memory = incident_memory or IncidentMemory()
        self.p105_prerequisite = p105_prerequisite

    def plan(self, case: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(case or {})
        route_override = payload.get("test_route")
        if route_override in {"allow", "deny", "escalate", "fallback"}:
            return self._result(
                "escalate" if route_override == "escalate" else "observe",
                [f"test_route:{route_override}; simulation-only boundary enforced"],
                audit_context={"test_route": route_override},
            )

        audit_context = _audit_context(payload)
        eligibility = self._eligibility(payload)
        if not eligibility["eligible"]:
            return self._result(
                str(eligibility["route"]),
                list(eligibility["reasons"]),
                audit_context=audit_context,
                escalation_payload=_mapping_or_empty(eligibility.get("escalation_payload")),
            )

        prerequisite = _validate_p105_artifact(payload, validator=self.p105_prerequisite)
        if not prerequisite["eligible"]:
            return self._result(
                "blocked_fail_closed",
                list(prerequisite["reasons"]),
                audit_context=audit_context,
            )

        try:
            composition = _load_registry_composition()
            self._assert_shared_policy_graph(composition)
        except (OSError, TypeError, ValueError, AssertionError) as exc:
            return self._result(
                "blocked_fail_closed",
                [f"capability registry composition failed closed: {exc}"],
                audit_context=audit_context,
            )

        capability_ids = _string_tuple(payload.get("advisory_capabilities", ()))
        if not capability_ids:
            return self._result(
                "observe",
                ["capability: no advisory preventive capabilities were supplied"],
                audit_context=audit_context,
            )

        family = str(payload.get("family", ""))
        candidates: list[dict[str, Any]] = []
        for capability_id in capability_ids:
            capability = composition.capabilities.get(capability_id)
            if capability is None:
                return self._result(
                    "escalate",
                    [f"capability: unsupported preventive capability {capability_id!r}"],
                    audit_context=audit_context,
                    escalation_payload={"unsupported_capability": capability_id},
                )
            if capability.family != family:
                continue
            try:
                compiled = self._compile(composition, capability_id, payload)
                candidates.append(self._evaluate_candidate(composition, compiled, payload))
            except (TypeError, ValueError) as exc:
                return self._result(
                    "blocked_fail_closed",
                    [f"capability {capability_id!r} failed closed during compilation: {exc}"],
                    audit_context=audit_context,
                )

        if not candidates:
            return self._result(
                "escalate",
                [f"capability: no registered capability supports family {family!r}"],
                audit_context=audit_context,
                escalation_payload={"family": family, "capabilities": list(capability_ids)},
            )

        ranked = _rank_candidates(candidates)
        selected = ranked[0]
        if not selected["eligible_for_intervention"]:
            gate_route = str(_get_nested(selected, ("safety_gate", "route"), "blocked_fail_closed"))
            route = gate_route if gate_route in {"observe", "escalate", "blocked_fail_closed"} else "blocked_fail_closed"
            return self._result(route, list(selected["reasons"]), audit_context=audit_context, candidates=ranked)

        return self._result(
            "plan",
            ["selected simulation-only preventive candidate", *selected["reasons"]],
            audit_context=audit_context,
            selected_candidate=selected,
            candidates=ranked,
        )

    def _eligibility(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        p104 = payload.get("p104_evidence")
        if not isinstance(p104, Mapping):
            return {"eligible": False, "route": "escalate", "reasons": ["p104: missing sufficient_for_policy_handoff evidence envelope"]}
        try:
            handoff = validate_p104_policy_handoff(p104)
        except (TypeError, ValueError, KeyError) as exc:
            return {
                "eligible": False,
                "route": "escalate",
                "reasons": [f"p104: canonical evidence envelope validation failed: {exc}"],
            }
        if p104.get("fresh") is not True:
            return {"eligible": False, "route": "observe", "reasons": ["stale p104 evidence; observe until refreshed"]}
        if not _string_tuple(handoff.get("citation_evidence_ids", ())):
            return {"eligible": False, "route": "escalate", "reasons": ["p104: missing validated citation evidence ids"]}
        if p104.get("conflicting_evidence") is True:
            return {"eligible": False, "route": "escalate", "reasons": ["conflicting p104 evidence requires operator review"]}
        if p104.get("natural_recovery") is True:
            return {"eligible": False, "route": "observe", "reasons": ["natural recovery evidence favors observe baseline"]}

        forecast = payload.get("forecast")
        if not isinstance(forecast, Mapping):
            return {"eligible": False, "route": "observe", "reasons": ["forecast: missing P105 qualified forecast"]}
        probability = _float(forecast.get("probability"), 0.0)
        if probability < _MIN_PROBABILITY:
            return {
                "eligible": False,
                "route": "observe",
                "reasons": [f"probability below intervention floor: {probability:.3f} < {_MIN_PROBABILITY:.3f}"],
            }
        if "false_alert_denominator" not in forecast:
            return {"eligible": False, "route": "observe", "reasons": ["forecast: missing false-alert denominator"]}
        family = str(payload.get("family", ""))
        if family not in _SUPPORTED_FAMILIES:
            return {
                "eligible": False,
                "route": "escalate",
                "reasons": [f"unsupported family {family!r}; no closed preventive planner route"],
            }
        return {"eligible": True, "route": "plan", "reasons": []}

    def _compile(self, composition: Any, capability_id: str, payload: Mapping[str, Any]) -> Any:
        p104 = _mapping_or_empty(payload.get("p104_evidence"))
        handoff = validate_p104_policy_handoff(p104)
        forecast = _mapping_or_empty(payload.get("forecast"))
        service = str(payload.get("service") or forecast.get("service") or "payment-api")
        environment = str(payload.get("environment") or forecast.get("environment") or "staging")
        approval = _mapping_or_empty(payload.get("approval_profile"))
        compiled = composition.compile_capability(
            capability_id,
            service=service,
            environment=environment,
            evidence_ids=list(_string_tuple(handoff.get("citation_evidence_ids", ()))),
            tenant_id=str(payload.get("tenant_id", "demo")),
            workspace_id=str(payload.get("workspace_id", "demo")),
            payload={
                "service": service,
                "simulation_only": True,
                "missing_preconditions": [],
            },
        )
        request = replace(
            compiled.action_request,
            incident_id=str(payload["incident_id"]) if payload.get("incident_id") else None,
            approved=bool(approval.get("approved", False)),
            approval_id=str(approval["approval_id"]) if approval.get("approval_id") else None,
        )
        context = replace(
            compiled.policy_context,
            severity=str(payload.get("severity", "medium")),
            confidence=_float(forecast.get("probability"), 0.0),
            conflicting_signals=bool(p104.get("conflicting_evidence", False)),
            known_ambiguity=bool(payload.get("known_ambiguity", False)),
            mode="preventive_planner",
        )
        return replace(compiled, action_request=request, policy_context=context)

    def _evaluate_candidate(self, composition: Any, compiled: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
        request = compiled.action_request
        policy = composition.policy_engine.evaluate(request, compiled.policy_context)
        blast = policy.blast_radius or composition.policy_engine.blast_radius_service.evaluate(request)
        simulation = policy.simulation or composition.policy_engine.action_simulator.simulate(request)
        memory_matches = self.incident_memory.search(
            service=compiled.policy_context.service,
            environment=compiled.policy_context.environment,
            fingerprint=str(payload.get("case_id", payload.get("family", "p106"))),
            root_cause=str(payload.get("family", "unknown")),
            runbook=compiled.capability.capability_id,
            action_type=request.action_type,
        )
        forecast = _mapping_or_empty(payload.get("forecast"))
        confidence = _float(forecast.get("probability"), 0.0)
        gate_input = {
            "request": request,
            "policy": policy,
            "policy_engine": composition.policy_engine,
            "blast_radius_service": composition.policy_engine.blast_radius_service,
            "action_simulator": composition.policy_engine.action_simulator,
            "blast_radius": blast,
            "simulation": simulation,
            "memory_matches": memory_matches,
            "confidence": confidence,
            "confidence_threshold": _SAFETY_CONFIDENCE_THRESHOLD,
            "service": compiled.policy_context.service,
            "environment": compiled.policy_context.environment,
            "severity": compiled.policy_context.severity,
            "conflicting_signals": compiled.policy_context.conflicting_signals,
            "known_ambiguity": compiled.policy_context.known_ambiguity,
            "registry_hash_parity": _registry_hash_parity(composition),
            "rollback_available": bool(getattr(blast, "rollback_available", False)),
        }
        gate_module = import_module("app.services.preventive_safety_gate")
        gate = gate_module.evaluate_preventive_safety_gate(gate_input)
        gate_dict = gate.to_dict() if callable(getattr(gate, "to_dict", None)) else _object_dict(gate)
        gate_passed = getattr(gate, "passed", gate_dict.get("passed")) is True

        ev = _score_expected_value(forecast, compiled.capability, blast_scope=str(getattr(blast, "scope", "unknown")))
        decision = policy.decision.value if isinstance(policy.decision, PolicyDecision) else str(policy.decision)
        reasons = [f"expected_value:{_float(ev.get('expected_value'), 0.0):.3f}", f"policy:{decision}", str(policy.reason)]
        reasons.extend(str(reason) for reason in gate_dict.get("reasons", ()) if str(reason) not in reasons)
        if failed_remediation_warning(memory_matches):
            reasons.append("incident_memory: prior failed remediation warning")
        eligible = bool(ev.get("eligible_for_intervention")) and gate_passed
        if not eligible and not reasons:
            reasons.append("preventive candidate failed closed")

        capability = compiled.capability
        return {
            "candidate_id": capability.capability_id,
            "capability_id": capability.capability_id,
            "action_request": _action_request_dict(request),
            "policy_context": _policy_context_dict(compiled.policy_context),
            "policy_decision": decision,
            "policy_reasons": list(policy.reasons),
            "risk_level": getattr(policy.risk_level, "value", str(policy.risk_level)),
            "evidence_links": list(_string_tuple(request.payload.get("evidence_ids", ()))),
            "preconditions": list(capability.preconditions or policy.preconditions),
            "simulation_result": simulation.to_dict(),
            "blast_radius": blast.to_dict(),
            "rollback_trigger": capability.rollback_trigger or "supersede generated advisory artifact",
            "canary_contract": _canary_contract(capability, request),
            "post_checks": list(capability.post_checks or policy.post_checks),
            "memory_summary": summarize_matches(memory_matches),
            "safety_gate": gate_dict,
            "expected_value": _float(ev.get("expected_value"), 0.0),
            "expected_value_components": _mapping_or_empty(ev.get("components")),
            "selected_baseline": str(ev.get("selected_baseline", "observe")),
            "eligible_for_intervention": eligible,
            "mutation_shaped": capability.mutation_shaped,
            "reversible": capability.reversible,
            "registry_hash": composition.registry_hash,
            "registry_parity_hash": composition.registry_hash,
            "reasons": reasons,
            "tie_break_trace": {
                "expected_value": _float(ev.get("expected_value"), 0.0),
                "blast_radius_order": _blast_order(str(getattr(blast, "scope", "unknown"))),
                "reversible": capability.reversible,
            },
            **_IMMUTABLE_BOUNDARY,
        }

    @staticmethod
    def _assert_shared_policy_graph(composition: Any) -> None:
        risk_engine = composition.risk_engine
        policy_engine = composition.policy_engine
        if not (
            policy_engine.risk_engine is risk_engine
            and policy_engine.blast_radius_service.risk_engine is risk_engine
            and policy_engine.action_simulator.risk_engine is risk_engine
        ):
            raise AssertionError("preventive registry composition does not share one RiskEngine")

    def _result(
        self,
        route: str,
        reasons: Sequence[str],
        *,
        audit_context: Mapping[str, Any] | None = None,
        selected_candidate: Mapping[str, Any] | None = None,
        candidates: Sequence[Mapping[str, Any]] | None = None,
        escalation_payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "route": route,
            "reasons": list(reasons),
            "operator_reasons": list(reasons),
            "selected_candidate": dict(selected_candidate) if selected_candidate else None,
            "candidates": [dict(candidate) for candidate in candidates or ()],
            "audit_context": dict(audit_context or {}),
            "escalation_payload": dict(escalation_payload or {}),
            **_IMMUTABLE_BOUNDARY,
        }


def _validate_p105_artifact(payload: Mapping[str, Any], *, validator: Any | None = None) -> dict[str, Any]:
    artifact_path = payload.get("p105_artifact_path") or payload.get("release_artifact_path")
    if not isinstance(artifact_path, (str, Path)) or not str(artifact_path):
        return {
            "eligible": False,
            "route": "blocked_fail_closed",
            "reasons": [
                "p105: canonical artifact path is required; embedded release booleans have no authority",
                "capability: candidate compilation is blocked until canonical p105 validation passes",
            ],
        }
    try:
        if validator is None:
            module = import_module("app.services.p105_release_prerequisite")
            validator = module.P106ReleasePrerequisite()
        validated = validator.validate(artifact_path)
    except (OSError, TypeError, ValueError, KeyError, AssertionError) as exc:
        return {
            "eligible": False,
            "route": "blocked_fail_closed",
            "reasons": [f"p105: canonical artifact validation failed closed: {exc}"],
        }
    qualified = getattr(validated, "release_qualified", False) is True
    unlocked = getattr(validated, "p106_unlocked", False) is True
    downstream_allowed = getattr(validated, "downstream_allowed", False) is True
    if not (qualified and unlocked and downstream_allowed):
        details = _string_tuple(getattr(validated, "reasons", ()))
        return {
            "eligible": False,
            "route": "blocked_fail_closed",
            "reasons": ["p105: path-validated prerequisite did not qualify and unlock P106", *details],
        }
    return {"eligible": True, "route": "plan", "reasons": []}


def validate_p104_policy_handoff(envelope: Mapping[str, Any]) -> Mapping[str, Any]:
    module = import_module("app.services.evidence_gap_investigator")
    if envelope.get("schema_version") != module.SCHEMA_VERSION:
        raise ValueError("P104 schema_version is not canonical")
    if envelope.get("boundary") != module.BOUNDARY:
        raise ValueError("P104 evidence envelope boundary is not exactly zero authority")
    validated = module.validate_decision_envelope(envelope)
    handoff = module.adapt_to_p100_policy_handoff(validated)
    if handoff.get("boundary") != {
        "read_only_tools_only": True,
        "production_mutation_enabled": False,
        "action_authority": False,
    }:
        raise ValueError("P104 handoff boundary is not exactly zero authority")
    return handoff


def _load_registry_composition() -> Any:
    module = import_module("app.services.preventive_capability_registry")
    return module.load_preventive_capability_registry(_CAPABILITY_REGISTRY_PATH)


def _registry_hash_parity(composition: Any) -> bool:
    if getattr(composition, "registry_hash_parity", None) is not True:
        return False
    parity_hashes = getattr(composition, "registry_parity_hashes", None)
    if not isinstance(parity_hashes, Mapping) or not parity_hashes:
        return False
    canonical_values = {str(value) for value in parity_hashes.values()}
    return canonical_values == {str(composition.registry_hash)}


def _score_expected_value(forecast: Mapping[str, Any], capability: Any, *, blast_scope: str) -> dict[str, Any]:
    probability = _float(forecast.get("probability"), 0.0)
    avoided = _float(forecast.get("avoided_impact"), 0.0)
    uncertainty = _float(forecast.get("uncertainty"), 0.0)
    denominator = _float(forecast.get("false_alert_denominator"), 1.0)
    module = import_module("app.services.preventive_expected_value")
    score = module.score_preventive_candidate(
        probability=probability,
        avoided_impact=avoided,
        intervention_harm=_float(capability.intervention_cost, 0.0),
        operational_cost=0.0,
        uncertainty_penalty=round(uncertainty * avoided, 6),
        false_alert_penalty=round(1.0 / max(denominator, 1.0), 6),
        reversible=capability.reversible,
    )
    result = _object_dict(score)
    reasons = list(_string_tuple(result.get("reasons", ())))
    if blast_scope in {"tenant", "global", "unknown", "prohibited"}:
        reasons.append(f"unsafe blast radius {blast_scope}")
        result["eligible_for_intervention"] = False
    result["reasons"] = reasons
    return result


def _rank_candidates(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (dict(candidate) for candidate in candidates),
        key=lambda candidate: (
            not bool(candidate.get("eligible_for_intervention")),
            -_float(candidate.get("expected_value"), 0.0),
            _blast_order(str(_get_nested(candidate, ("blast_radius", "scope"), "unknown"))),
            not bool(candidate.get("reversible", False)),
            str(candidate.get("candidate_id", "")),
        ),
    )


def _canary_contract(capability: Any, request: ActionRequest) -> dict[str, Any]:
    template = capability.canary_scope_template
    if isinstance(template, Mapping):
        contract = dict(template)
    else:
        contract = {
            "treatment_selector": f"local:{request.target}:advisory",
            "control_selector": f"control:{request.target}:holdout",
            "duration_minutes": 30,
            "primary_metric": "forecasted_failure_rate",
            "guardrail_metrics": ["error_rate", "latency_p95", "operator_escalations"],
        }
    contract.update(
        {
            "rollback_trigger": capability.rollback_trigger or "supersede generated advisory artifact",
            "post_checks": list(capability.post_checks),
            "p107_handoff_required": True,
            "execution_enabled": False,
            "simulation_only": True,
        }
    )
    return contract


def _audit_context(payload: Mapping[str, Any]) -> dict[str, Any]:
    approval = _mapping_or_empty(payload.get("approval_profile"))
    return {
        "case_id": payload.get("case_id"),
        "family": payload.get("family"),
        "approval_profile": dict(approval),
        "p105_artifact_path": payload.get("p105_artifact_path") or payload.get("release_artifact_path"),
        "boundary": dict(_IMMUTABLE_BOUNDARY),
    }


def _action_request_dict(request: ActionRequest) -> dict[str, Any]:
    data = asdict(request)
    data["payload"] = dict(request.payload)
    return data


def _policy_context_dict(context: PolicyContext) -> dict[str, Any]:
    return {
        "capabilities": sorted(context.capabilities),
        "service": context.service,
        "environment": context.environment,
        "tenant_id": context.tenant_id,
        "workspace_id": context.workspace_id,
        "severity": context.severity,
        "mode": context.mode,
        "confidence": context.confidence,
        "evidence_count": context.evidence_count,
    }


def _object_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value)
    return ()


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_nested(data: Mapping[str, Any], path: Sequence[str], default: Any) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, Mapping):
            return default
        current = current.get(key, default)
    return current


def _blast_order(scope: str) -> int:
    return {"local": 0, "service": 1, "workspace": 2, "tenant": 3, "global": 4, "unknown": 5, "prohibited": 6}.get(scope, 5)
