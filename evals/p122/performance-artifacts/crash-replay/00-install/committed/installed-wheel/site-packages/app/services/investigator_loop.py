"""P46 operator-like investigator loop."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.evidence_grounded_judgment import validate_judgment_contract
from app.services.redaction import redact_value

_BOUNDARY = {
    "offline_fixture_only": True,
    "read_only_investigation_planning": True,
    "live_api_calls_enabled": False,
    "auth_session_work_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}
_HYPOTHESES = {
    "recent_deploy_regression": ["deploy", "version", "pod", "timeout", "5xx"],
    "database_saturation": ["db", "pool", "connection", "slow", "latency"],
    "external_dependency_degraded": ["dependency", "provider", "upstream", "timeout", "rate_limit"],
    "traffic_spike": ["traffic", "rps", "bot", "load", "autoscale"],
    "false_positive_or_noise": ["normal", "unchanged", "low", "sporadic", "slo"],
}
_NEXT_INVESTIGATIONS = {
    "recent_deploy_regression": ["query pod/version error distribution", "check deploy diff", "simulate rollback blast radius"],
    "database_saturation": ["query connection pool wait", "sample slow queries", "check DB CPU and lock waits"],
    "external_dependency_degraded": ["check provider status", "query dependency timeout rate", "inspect retry/circuit breaker state"],
    "traffic_spike": ["query RPS by route", "check autoscaling events", "inspect bot/user-agent distribution"],
    "false_positive_or_noise": ["verify user impact", "check SLO burn", "compare independent telemetry sources"],
}


@dataclass(frozen=True)
class InvestigatorLoopReport:
    incidents: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        hypothesis_count = sum(len(item["hypotheses"]) for item in self.incidents)
        grounded = sum(1 for item in self.incidents for hyp in item["hypotheses"] if hyp["contract"]["valid"])
        top_matches = sum(1 for item in self.incidents if item["top_hypothesis"] == item["expected_top_hypothesis"])
        unsafe = sum(1 for item in self.incidents for hyp in item["hypotheses"] if hyp["action_boundary"]["auto_execute_allowed"])
        payload = {
            "summary": {
                "incident_count": len(self.incidents),
                "hypothesis_count": hypothesis_count,
                "grounded_hypothesis_ratio": _ratio(grounded, hypothesis_count),
                "top_hypothesis_match_ratio": _ratio(top_matches, len(self.incidents)),
                "unsafe_action_count": unsafe,
                "passed": bool(self.incidents) and grounded == hypothesis_count and top_matches == len(self.incidents) and unsafe == 0,
            },
            "boundary": dict(_BOUNDARY),
            "incidents": list(self.incidents),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def build_investigator_loop_report(cases_path: str | Path) -> InvestigatorLoopReport:
    incidents = _load_incidents(cases_path)
    return InvestigatorLoopReport(tuple(_investigate(incident) for incident in incidents))


def render_investigator_loop_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    lines = [
        "# OpsCat Investigator Loop",
        "",
        "Observe → hypothesize → bind evidence → plan next read-only investigations → gate actions.",
        "",
        "## Summary",
        f"- Incidents: {summary.get('incident_count')}",
        f"- Hypotheses: {summary.get('hypothesis_count')}",
        f"- Grounded hypothesis ratio: {summary.get('grounded_hypothesis_ratio')}",
        f"- Top hypothesis match ratio: {summary.get('top_hypothesis_match_ratio')}",
        f"- Unsafe actions: {summary.get('unsafe_action_count')}",
        "",
        "## Incidents",
    ]
    for incident in _sequence(payload.get("incidents", ())):
        if isinstance(incident, Mapping):
            lines.append(f"- `{incident.get('incident_id')}` top={incident.get('top_hypothesis')}")
            top = _mapping(_sequence(incident.get("hypotheses", ()))[0]) if _sequence(incident.get("hypotheses", ())) else {}
            lines.append(f"  - Next investigations: {', '.join(str(x) for x in _sequence(top.get('next_investigations', ())))}")
    return "\n".join(lines) + "\n"


def write_investigator_loop_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_investigator_loop_markdown(payload), encoding="utf-8")


def _load_incidents(path: str | Path) -> tuple[Mapping[str, Any], ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("P46 cases must be a mapping")
    return tuple(item for item in _sequence(data.get("incidents", ())) if isinstance(item, Mapping))


def _investigate(incident: Mapping[str, Any]) -> dict[str, Any]:
    signals = tuple(item for item in _sequence(incident.get("signals", ())) if isinstance(item, Mapping))
    hypotheses = sorted((_hypothesis(name, signals) for name in _HYPOTHESES), key=lambda item: item["priority"], reverse=True)
    return {
        "incident_id": str(incident.get("id", "p46-incident")),
        "title": str(incident.get("title", "incident")),
        "expected_top_hypothesis": str(incident.get("expected_top_hypothesis", "unknown")),
        "top_hypothesis": hypotheses[0]["name"] if hypotheses else "none",
        "hypotheses": hypotheses,
    }


def _hypothesis(name: str, signals: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    keywords = _HYPOTHESES[name]
    supporting = [_evidence(signal) for signal in signals if _matches(signal, keywords)]
    counter = [_evidence(signal) for signal in signals if not _matches(signal, keywords)][:3]
    missing = _missing_for(name, supporting)
    priority = _priority(supporting, counter, missing)
    boundary = {
        "route": "approval_required" if priority >= 0.65 else "human_required",
        "auto_execute_allowed": False,
        "approval_required": priority >= 0.65,
        "safe_actions": ["run read-only query", "collect corroborating telemetry", "draft response plan"],
        "blocked_actions": ["production rollback", "restart production", "write config", "run shell command"],
    }
    judgment = {
        "claim": name,
        "supporting_evidence": supporting or [_synthetic_evidence("missing_support", name)],
        "counter_evidence": counter or [_synthetic_evidence("no_counter", name)],
        "missing_evidence": missing,
        "confidence": priority,
        "action_boundary": boundary,
    }
    return {
        "name": name,
        "priority": priority,
        "supporting_evidence": judgment["supporting_evidence"],
        "counter_evidence": judgment["counter_evidence"],
        "missing_evidence": missing,
        "next_investigations": _NEXT_INVESTIGATIONS[name],
        "action_boundary": boundary,
        "contract": validate_judgment_contract(judgment),
    }


def _matches(signal: Mapping[str, Any], keywords: Sequence[str]) -> bool:
    signal_name = str(signal.get("signal", "")).lower()
    value = str(signal.get("value", "")).lower()
    if "deploy" in signal_name and value in {"none", "no", "false", "n/a"}:
        return False
    text = " ".join(str(signal.get(key, "")) for key in ("source", "signal", "value")).lower()
    return any(keyword in text for keyword in keywords)


def _evidence(signal: Mapping[str, Any]) -> dict[str, str]:
    return {"source": str(signal.get("source", "unknown")), "signal": str(signal.get("signal", "unknown")), "value": str(signal.get("value", "")), "strength": str(signal.get("strength", "low"))}


def _synthetic_evidence(kind: str, name: str) -> dict[str, str]:
    return {"source": "investigator", "signal": kind, "value": f"{name} requires more read-only evidence", "strength": "low"}


def _missing_for(name: str, supporting: Sequence[Mapping[str, Any]]) -> list[str]:
    if name == "recent_deploy_regression":
        required = ["rollback simulation", "deploy diff"]
    elif name == "database_saturation":
        required = ["slow query sample", "connection pool limit"]
    elif name == "external_dependency_degraded":
        required = ["provider status", "dependency timeout distribution"]
    elif name == "traffic_spike":
        required = ["bot distribution", "autoscaling event"]
    else:
        required = ["customer impact", "independent telemetry confirmation"]
    return required[: max(1, 2 - len(supporting))]


def _priority(supporting: Sequence[Mapping[str, Any]], counter: Sequence[Mapping[str, Any]], missing: Sequence[str]) -> float:
    score = 0.25 + 0.18 * len(supporting) - 0.03 * len(counter) - 0.04 * len(missing)
    return round(max(0.05, min(0.95, score)), 2)


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 3)
