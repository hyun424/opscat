"""P48 hypothesis re-ranking with anti-anchoring evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.redaction import redact_value

_BOUNDARY = {
    "offline_fixture_only": True,
    "read_only_investigation_results_only": True,
    "live_api_calls_enabled": False,
    "auth_session_work_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}
_SUPPORT_DELTA = {"low": 0.06, "medium": 0.1, "high": 0.18}
_COUNTER_DELTA = {"low": -0.08, "medium": -0.14, "high": -0.25}


@dataclass(frozen=True)
class HypothesisRerankerReport:
    cases: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        expected_matches = sum(1 for case in self.cases if case["final_top"] == case["expected_final_top"])
        demotions = sum(1 for case in self.cases if case["initial_top"] != case["final_top"])
        unsafe = sum(1 for case in self.cases if case["action_boundary"]["auto_execute_allowed"])
        payload = {
            "summary": {
                "case_count": len(self.cases),
                "expected_top_match_count": expected_matches,
                "expected_top_match_ratio": _ratio(expected_matches, len(self.cases)),
                "anti_anchoring_demotions": demotions,
                "unsafe_action_count": unsafe,
                "passed": bool(self.cases) and expected_matches == len(self.cases) and unsafe == 0,
            },
            "boundary": dict(_BOUNDARY),
            "cases": list(self.cases),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def build_hypothesis_reranker_report(cases_path: str | Path) -> HypothesisRerankerReport:
    return HypothesisRerankerReport(tuple(_rerank_case(case) for case in _load_cases(cases_path)))


def render_hypothesis_reranker_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    lines = [
        "# OpsCat Hypothesis Re-ranker",
        "",
        "Updates hypothesis confidence after read-only investigation results and records anti-anchoring behavior.",
        "",
        "## Summary",
        f"- Cases: {summary.get('case_count')}",
        f"- Expected top match ratio: {summary.get('expected_top_match_ratio')}",
        f"- Anti-anchoring demotions: {summary.get('anti_anchoring_demotions')}",
        f"- Unsafe actions: {summary.get('unsafe_action_count')}",
        "",
        "## Anti-anchoring cases",
    ]
    for case in _sequence(payload.get("cases", ())) :
        if isinstance(case, Mapping):
            lines.append(
                f"- `{case.get('case_id')}` initial={case.get('initial_top')} final={case.get('final_top')} expected={case.get('expected_final_top')}"
            )
            lines.append(f"  - Changed: {case.get('initial_top') != case.get('final_top')}")
    lines.extend(["", "## Action boundary", "- Re-ranking can update recommendations, but production action remains approval-gated."])
    return "\n".join(lines) + "\n"


def write_hypothesis_reranker_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_hypothesis_reranker_markdown(payload), encoding="utf-8")


def _load_cases(path: str | Path) -> tuple[Mapping[str, Any], ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("P48 cases must be a mapping")
    return tuple(item for item in _sequence(data.get("cases", ())) if isinstance(item, Mapping))


def _rerank_case(case: Mapping[str, Any]) -> dict[str, Any]:
    observations = tuple(item for item in _sequence(case.get("observations", ())) if isinstance(item, Mapping))
    updated = (
        _updated_hypothesis(hypothesis, observations)
        for hypothesis in _sequence(case.get("hypotheses", ()))
        if isinstance(hypothesis, Mapping)
    )
    ranked = sorted(updated, key=lambda item: item["updated_confidence"], reverse=True)
    final_top = str(ranked[0]["name"]) if ranked else "none"
    initial_top = str(case.get("initial_top", "none"))
    expected = str(case.get("expected_final_top", "none"))
    conflicting = any(hyp["counter_evidence"] for hyp in ranked)
    top_confidence = float(ranked[0]["updated_confidence"]) if ranked else 0.0
    route = "approval_required" if top_confidence >= 0.7 and not conflicting else "human_required"
    return {
        "case_id": str(case.get("id", "p48-case")),
        "initial_top": initial_top,
        "final_top": final_top,
        "expected_final_top": expected,
        "changed_top": initial_top != final_top,
        "ranked_hypotheses": ranked,
        "observations": [_observation(item) for item in observations],
        "action_boundary": {
            "route": route,
            "auto_execute_allowed": False,
            "approval_required": route == "approval_required",
            "safe_actions": ["collect additional read-only evidence", "update incident note", "draft remediation proposal"],
            "blocked_actions": ["production rollback", "restart production", "write config", "run shell command"],
        },
    }


def _updated_hypothesis(hypothesis: Mapping[str, Any], observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    name = str(hypothesis.get("name", "unknown"))
    baseline = _float(hypothesis.get("confidence"), 0.0)
    matching = [obs for obs in observations if str(obs.get("target", "")) == name]
    support = [_observation(obs) for obs in matching if str(obs.get("type", "")) == "support"]
    counter = [_observation(obs) for obs in matching if str(obs.get("type", "")) == "counter"]
    missing = [str(item) for item in _sequence(hypothesis.get("missing", ()))]
    delta = sum(_SUPPORT_DELTA.get(item["strength"], 0.06) for item in support)
    delta += sum(_COUNTER_DELTA.get(item["strength"], -0.08) for item in counter)
    delta -= 0.02 * len(missing)
    updated = _clamp(round(baseline + delta, 3))
    return {
        "name": name,
        "baseline_confidence": baseline,
        "updated_confidence": updated,
        "delta": round(updated - baseline, 3),
        "supporting_evidence": [str(item) for item in _sequence(hypothesis.get("support", ()))],
        "counter_signals": [str(item) for item in _sequence(hypothesis.get("counter", ()))],
        "missing_evidence": missing,
        "new_supporting_evidence": support,
        "counter_evidence": counter,
    }


def _observation(item: Mapping[str, Any]) -> dict[str, str]:
    return {
        "target": str(item.get("target", "unknown")),
        "type": str(item.get("type", "unknown")),
        "evidence": str(item.get("evidence", "")),
        "strength": str(item.get("strength", "low")),
    }


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float) -> float:
    return round(max(0.05, min(0.95, value)), 3)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 3)
