"""Strict mock-by-default LLM advisory validator for P106.

LLM packets are advisory only. They may name already registered preventive
capabilities, but cannot provide action authority, policy overrides, expected
value, raw confidence, or P107 unlock signals.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ZERO_AUTHORITY = {
    "auth_enabled": False,
    "production_mutation_enabled": False,
    "action_authority": False,
    "remediation_execution_enabled": False,
    "default_external_model_calls": 0,
}

_FORBIDDEN_PROPOSAL_FIELDS = {
    "action_type",
    "raw_action_type",
    "policy_override",
    "raw_confidence_override",
    "confidence",
    "forecast_probability",
    "expected_value",
    "ev",
    "risk_score",
    "can_unlock_p107",
    "p107_unlocked",
}


def validate_llm_advisory_packet(packet: Mapping[str, Any], *, registry_path: str | Path) -> dict[str, Any]:
    reasons: list[str] = []
    registered = _registered_capabilities(registry_path)

    if packet.get("schema_version") != "p106.llm_advisory.v1":
        reasons.append("unsupported advisory schema")
    proposals = packet.get("proposals")
    if not isinstance(proposals, list):
        reasons.append("proposals must be a list")
        proposals = []

    seen: set[str] = set()
    accepted: list[dict[str, Any]] = []
    for index, proposal in enumerate(proposals):
        if not isinstance(proposal, Mapping):
            reasons.append(f"proposal[{index}] must be a mapping")
            continue
        capability_id = proposal.get("capability_id")
        if not isinstance(capability_id, str) or not capability_id:
            reasons.append(f"proposal[{index}] capability_id is required")
            continue
        if capability_id in seen:
            reasons.append(f"duplicate capability {capability_id}")
        seen.add(capability_id)
        if capability_id not in registered:
            reasons.append(f"unregistered capability {capability_id}")
        forbidden = sorted(_FORBIDDEN_PROPOSAL_FIELDS.intersection(proposal))
        if forbidden:
            reasons.append(f"{capability_id} contains forbidden advisory fields: {', '.join(forbidden)}")
        target_environment = str(proposal.get("target_environment", "")).lower()
        if target_environment in {"prod", "production"}:
            reasons.append(f"{capability_id} targets production")
        rationale = proposal.get("rationale")
        accepted.append({"capability_id": capability_id, "rationale": rationale if isinstance(rationale, str) else ""})

    valid = not reasons
    return {
        "valid": valid,
        "route": "advisory_registered_capabilities_only" if valid else "deterministic_fallback",
        "accepted_proposals": accepted if valid else [],
        "reasons": reasons,
        "can_override_policy": False,
        "can_set_expected_value": False,
        "can_unlock_p107": False,
        **ZERO_AUTHORITY,
        "authority": dict(ZERO_AUTHORITY),
    }


def _registered_capabilities(path: str | Path) -> set[str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    capabilities = data.get("capabilities", [])
    return {
        item["capability_id"]
        for item in capabilities
        if isinstance(item, Mapping) and isinstance(item.get("capability_id"), str)
    }
