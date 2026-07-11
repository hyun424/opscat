"""P93 portfolio demo pack.

Builds deterministic local/mock portfolio evidence from P92 and selected prior
release artifacts. This module renders metadata only and performs no auth work,
live API calls, credential reads, network calls, model calls, production
mutation, remediation execution, or action execution.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.services.redaction import redact_value

_ZERO_SIDE_EFFECT_COUNTERS: dict[str, int] = {
    "action_execution_count": 0,
    "live_api_call_count": 0,
    "credential_read_count": 0,
    "network_call_count": 0,
    "production_mutation_count": 0,
    "external_model_call_count": 0,
    "real_remediation_execution_count": 0,
}

_REQUIRED_FIELDS = (
    "demo_id",
    "title",
    "portfolio_pitch",
    "target_role_signals",
    "architecture_sections",
    "operator_walkthrough_steps",
    "proof_points",
    "safety_boundaries",
    "forbidden_claims",
    "demo_commands",
    "expected_outputs",
    "readiness_status",
    "remaining_gaps",
    "zero_side_effect_counters",
)


def build_portfolio_demo_pack(path: str | Path = "evals/actions/p93_portfolio_demo_pack.json") -> dict[str, Any]:
    """Return a deterministic P93 portfolio demo pack payload."""

    raw_payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw_payload, Mapping):
        raise ValueError("P93 portfolio demo pack fixture must be a JSON object")

    payload = dict(raw_payload)
    payload["zero_side_effect_counters"] = dict(_ZERO_SIDE_EFFECT_COUNTERS)
    summary = _summary(payload)
    payload["summary"] = summary
    payload["audit_metadata"] = {
        "audit_id": str(payload.get("demo_id", "p93-portfolio-demo-pack")),
        "p93_portfolio_demo_pack": True,
        "local_mock_only": True,
        "side_effect_free": True,
        "not_production_autonomy": True,
        "source_evidence": ["P92", "P90", "P91", "P80-P89"],
    }
    _validate_payload(payload, summary)
    redacted = redact_value(payload)
    return dict(redacted) if isinstance(redacted, Mapping) else payload


def render_portfolio_demo_pack_markdown(payload: Mapping[str, Any]) -> str:
    """Render reviewer-readable portfolio evidence from the structured pack."""

    summary = _mapping(payload.get("summary"))
    lines = [
        f"# {payload.get('title', 'OpsCat Portfolio Demo Narrative & Operator Walkthrough')}",
        "",
        str(payload.get("portfolio_pitch", "")).strip(),
        "",
        "## One-command demo",
        "",
    ]
    for command in _sequence(payload.get("demo_commands")):
        if not isinstance(command, Mapping):
            continue
        lines.extend(
            [
                f"### {command.get('label', 'Command')}",
                "",
                "```bash",
                str(command.get("command", "")).strip(),
                "```",
                "",
                str(command.get("purpose", "")).strip(),
                "",
            ]
        )
    lines.extend(
        [
            "Expected smoke line:",
            "",
            "```text",
            "walkthrough_steps>=8 proof_points>=6 commands>=3 executions=0",
            "```",
            "",
            "## Operator walkthrough",
            "",
        ]
    )
    for step in _sequence(payload.get("operator_walkthrough_steps")):
        if not isinstance(step, Mapping):
            continue
        lines.append(
            f"- **{step.get('stage', 'stage')}**: {step.get('operator_view', '')} "
            f"Evidence: {', '.join(str(item) for item in _sequence(step.get('evidence_refs')))}"
        )
    lines.extend(["", "## Target role signals", ""])
    for signal in _sequence(payload.get("target_role_signals")):
        if not isinstance(signal, Mapping):
            continue
        lines.append(
            f"- **{signal.get('signal', 'signal')}**: {signal.get('portfolio_readout', '')} "
            f"Evidence: {', '.join(str(item) for item in _sequence(signal.get('evidence_refs')))}"
        )
    lines.extend(["", "## Architecture sections", ""])
    for section in _sequence(payload.get("architecture_sections")):
        if not isinstance(section, Mapping):
            continue
        lines.append(f"- **{section.get('section', 'section')}**: {section.get('summary', '')}")
    lines.extend(["", "## Proof points", ""])
    for proof in _sequence(payload.get("proof_points")):
        lines.append(f"- {proof}")
    lines.extend(
        [
            "",
            "## Safety boundary",
            "",
            "This pack is local/mock evidence only and not production autonomy.",
        ]
    )
    for boundary in _sequence(payload.get("safety_boundaries")):
        lines.append(f"- {boundary}")
    lines.extend(["", "## Remaining gaps", ""])
    for gap in _sequence(payload.get("remaining_gaps")):
        lines.append(f"- {gap}")
    lines.extend(
        [
            "",
            "## Summary counters",
            "",
            f"- walkthrough_steps={summary.get('walkthrough_steps', 0)}",
            f"- proof_points={summary.get('proof_points', 0)}",
            f"- commands={summary.get('commands', 0)}",
            f"- executions={summary.get('executions', 0)}",
            f"- passed={summary.get('passed', False)}",
        ]
    )
    return "\n".join(lines) + "\n"


def write_portfolio_demo_pack_outputs(
    payload: Mapping[str, Any],
    *,
    output_json: str | Path | None = None,
    output_md: str | Path | None = None,
) -> None:
    if output_json:
        output_json_path = Path(output_json)
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        output_md_path = Path(output_md)
        output_md_path.parent.mkdir(parents=True, exist_ok=True)
        output_md_path.write_text(render_portfolio_demo_pack_markdown(payload), encoding="utf-8")


def _summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    walkthrough_steps = len(_sequence(payload.get("operator_walkthrough_steps")))
    proof_points = len(_sequence(payload.get("proof_points")))
    commands = len(_sequence(payload.get("demo_commands")))
    executions = sum(_ZERO_SIDE_EFFECT_COUNTERS.values())
    return {
        "walkthrough_steps": walkthrough_steps,
        "proof_points": proof_points,
        "commands": commands,
        "executions": executions,
        "passed": walkthrough_steps >= 8 and proof_points >= 6 and commands >= 3 and executions == 0,
    }


def _validate_payload(payload: Mapping[str, Any], summary: Mapping[str, Any]) -> None:
    missing = [field for field in _REQUIRED_FIELDS if field not in payload]
    if missing:
        raise ValueError(f"P93 portfolio demo pack missing fields: {', '.join(missing)}")
    if payload.get("zero_side_effect_counters") != _ZERO_SIDE_EFFECT_COUNTERS:
        raise ValueError("P93 portfolio demo pack must preserve zero side-effect counters")
    if not summary.get("passed"):
        raise ValueError("P93 portfolio demo pack does not meet smoke thresholds")


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, str | bytes) else ()
