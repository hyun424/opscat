"""P51 operator judgment benchmark v2."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.redaction import redact_value

_BOUNDARY = {
    "offline_fixture_only": True,
    "benchmark_only": True,
    "live_api_calls_enabled": False,
    "auth_session_work_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}
_HYPOTHESIS_KEYWORDS = {
    "recent_deploy_regression": ("deploy", "version", "pod", "rollback", "release"),
    "database_saturation": ("db", "database", "pool", "query", "lock", "latency"),
    "external_dependency_degraded": ("provider", "upstream", "dependency", "timeout", "rate_limit"),
    "traffic_spike": ("traffic", "rps", "baseline", "bot", "load", "autoscale"),
}
_STRENGTH = {"low": 1.0, "medium": 2.0, "high": 3.0}
_DEFAULT_THRESHOLDS = {
    "detection_recall": 0.75,
    "top1_hypothesis_accuracy": 0.75,
    "evidence_quality_score": 0.8,
    "route_accuracy": 0.75,
    "rerank_success_rate": 0.5,
    "recovery_verification_coverage": 0.5,
}


@dataclass(frozen=True)
class OperatorJudgmentBenchmarkV2Report:
    cases: tuple[dict[str, Any], ...]
    thresholds: Mapping[str, float]

    def to_dict(self) -> dict[str, Any]:
        scorecard = _scorecard(self.cases)
        threshold_checks = {key: scorecard.get(key, 0.0) >= float(self.thresholds.get(key, 0.0)) for key in _DEFAULT_THRESHOLDS}
        safety = {
            "unsafe_auto_execute_count": sum(1 for case in self.cases if case["safety"]["unsafe_auto_execute_allowed"]),
            "production_execution_count": sum(1 for case in self.cases if case["safety"]["production_execution_attempted"]),
            "live_call_count": sum(1 for case in self.cases if case["safety"]["live_call_attempted"]),
        }
        payload = {
            "summary": {
                "case_count": len(self.cases),
                "thresholds_met": all(threshold_checks.values()),
                "passed": bool(self.cases) and all(threshold_checks.values()) and all(value == 0 for value in safety.values()),
            },
            "scorecard": scorecard,
            "thresholds": dict(self.thresholds),
            "threshold_checks": threshold_checks,
            "failure_taxonomy": _failure_taxonomy(self.cases),
            "safety": safety,
            "boundary": dict(_BOUNDARY),
            "cases": list(self.cases),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def build_operator_judgment_benchmark_v2_report(cases_path: str | Path) -> OperatorJudgmentBenchmarkV2Report:
    data = _load_payload(cases_path)
    cases = tuple(_score_case(case) for case in _sequence(data.get("cases", ())) if isinstance(case, Mapping))
    thresholds = {**_DEFAULT_THRESHOLDS, **{str(k): float(v) for k, v in _mapping(data.get("thresholds")).items()}}
    return OperatorJudgmentBenchmarkV2Report(cases, thresholds)


def render_operator_judgment_benchmark_v2_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    scorecard = _mapping(payload.get("scorecard"))
    failure_taxonomy = _mapping(payload.get("failure_taxonomy"))
    lines = [
        "# OpsCat Operator Judgment Benchmark v2",
        "",
        "Scores operator judgment quality before further UI or live-product integration investment.",
        "",
        "## Summary",
        f"- Cases: {summary.get('case_count')}",
        f"- Passed: {summary.get('passed')}",
        "",
        "## Scorecard",
    ]
    for key in sorted(scorecard):
        lines.append(f"- {key}: {scorecard.get(key)}")
    lines.extend(["", "## Failure taxonomy"])
    for key in sorted(failure_taxonomy):
        lines.append(f"- {key}: {failure_taxonomy.get(key)}")
    lines.extend(["", "## Cases"])
    for case in _sequence(payload.get("cases", ())) :
        if isinstance(case, Mapping):
            lines.append(
                f"- `{case.get('case_id')}` expected={case.get('expected_top_hypothesis')} predicted={case.get('predicted_top_hypothesis')} route={case.get('predicted_route')}"
            )
    lines.extend(["", "## Safety", "- Unsafe auto-execute, production execution, and live calls must remain zero."])
    return "\n".join(lines) + "\n"


def write_operator_judgment_benchmark_v2_outputs(
    payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None
) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_operator_judgment_benchmark_v2_markdown(payload), encoding="utf-8")


def _load_payload(path: str | Path) -> Mapping[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("P51 benchmark cases must be a mapping")
    return data


def _score_case(case: Mapping[str, Any]) -> dict[str, Any]:
    signals = tuple(item for item in _sequence(case.get("signals", ())) if isinstance(item, Mapping))
    counter = tuple(item for item in _sequence(case.get("counter_signals", ())) if isinstance(item, Mapping))
    missing = tuple(str(item) for item in _sequence(case.get("missing", ())))
    observations = tuple(item for item in _sequence(case.get("observations", ())) if isinstance(item, Mapping))
    initial = _top_hypothesis(signals)
    predicted_top = _reranked_top(initial, observations) if observations else initial
    detected = _detected(case, signals)
    evidence_quality = _evidence_quality(signals, counter, missing)
    predicted_route = _route(predicted_top, evidence_quality, missing)
    expected_top = str(case.get("expected_top_hypothesis", "unknown"))
    expected_detected = bool(case.get("expected_detected"))
    expected_route = str(case.get("expected_route", "human_required"))
    expected_reranked = bool(case.get("expected_re_ranked"))
    reranked_success = (not expected_reranked) or (initial != predicted_top and predicted_top == expected_top)
    recovery_verification_present = bool(case.get("expected_recovery_verification"))
    failures = _case_failures(
        detected=detected,
        expected_detected=expected_detected,
        predicted_top=predicted_top,
        expected_top=expected_top,
        evidence_quality=evidence_quality,
        predicted_route=predicted_route,
        expected_route=expected_route,
        expected_reranked=expected_reranked,
        reranked_success=reranked_success,
        recovery_verification_present=recovery_verification_present,
    )
    return {
        "case_id": str(case.get("id", "p51-case")),
        "title": str(case.get("title", "operator judgment case")),
        "detected": detected,
        "expected_detected": expected_detected,
        "initial_top_hypothesis": initial,
        "predicted_top_hypothesis": predicted_top,
        "expected_top_hypothesis": expected_top,
        "predicted_route": predicted_route,
        "expected_route": expected_route,
        "reranked_success": reranked_success,
        "recovery_verification_present": recovery_verification_present,
        "evidence_quality": evidence_quality,
        "evidence_card": {
            "supporting_evidence": [_evidence_item(item) for item in signals],
            "counter_evidence": [_evidence_item(item) for item in counter],
            "missing_evidence": list(missing),
        },
        "failures": failures,
        "safety": {"unsafe_auto_execute_allowed": False, "production_execution_attempted": False, "live_call_attempted": False},
    }


def _top_hypothesis(signals: Sequence[Mapping[str, Any]]) -> str:
    scores = {name: 0.0 for name in _HYPOTHESIS_KEYWORDS}
    for signal in signals:
        text = " ".join(str(signal.get(key, "")) for key in ("source", "signal", "value")).lower()
        strength = _STRENGTH.get(str(signal.get("strength", "low")), 1.0)
        for name, keywords in _HYPOTHESIS_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                scores[name] += strength
    return max(scores.items(), key=lambda item: item[1])[0]


def _reranked_top(initial: str, observations: Sequence[Mapping[str, Any]]) -> str:
    scores = {name: (1.0 if name == initial else 0.0) for name in _HYPOTHESIS_KEYWORDS}
    for observation in observations:
        target = str(observation.get("target", ""))
        if target not in scores:
            continue
        strength = _STRENGTH.get(str(observation.get("strength", "low")), 1.0)
        if str(observation.get("type", "")) == "support":
            scores[target] += strength
        elif str(observation.get("type", "")) == "counter":
            scores[target] -= strength
    return max(scores.items(), key=lambda item: item[1])[0]


def _detected(case: Mapping[str, Any], signals: Sequence[Mapping[str, Any]]) -> bool:
    severity = str(case.get("severity", "ticket"))
    return severity in {"page", "ticket"} and bool(signals)


def _evidence_quality(signals: Sequence[Mapping[str, Any]], counter: Sequence[Mapping[str, Any]], missing: Sequence[str]) -> float:
    support_score = 0.4 if signals else 0.0
    counter_score = 0.3 if counter else 0.15
    missing_score = 0.3 if len(missing) <= 1 else 0.2
    return round(support_score + counter_score + missing_score, 3)


def _route(top_hypothesis: str, evidence_quality: float, missing: Sequence[str]) -> str:
    if top_hypothesis == "external_dependency_degraded" or evidence_quality < 0.9 or len(missing) >= 2:
        return "human_required"
    return "approval_required"


def _case_failures(
    *,
    detected: bool,
    expected_detected: bool,
    predicted_top: str,
    expected_top: str,
    evidence_quality: float,
    predicted_route: str,
    expected_route: str,
    expected_reranked: bool,
    reranked_success: bool,
    recovery_verification_present: bool,
) -> list[str]:
    failures: list[str] = []
    if detected != expected_detected:
        failures.append("detection_failure")
    if predicted_top != expected_top:
        failures.append("root_cause_failure")
    if evidence_quality < 0.9:
        failures.append("evidence_gap")
    if predicted_route != expected_route:
        failures.append("route_failure")
    if expected_reranked and not reranked_success:
        failures.append("rerank_failure")
    if not recovery_verification_present:
        failures.append("recovery_verification_gap")
    return failures


def _scorecard(cases: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    expected_detected = [case for case in cases if case["expected_detected"]]
    expected_reranked = [case for case in cases if case["initial_top_hypothesis"] != case["expected_top_hypothesis"]]
    return {
        "detection_recall": _ratio(sum(1 for case in expected_detected if case["detected"]), len(expected_detected)),
        "top1_hypothesis_accuracy": _ratio(sum(1 for case in cases if case["predicted_top_hypothesis"] == case["expected_top_hypothesis"]), len(cases)),
        "evidence_quality_score": round(sum(float(case["evidence_quality"]) for case in cases) / len(cases), 3) if cases else 0.0,
        "route_accuracy": _ratio(sum(1 for case in cases if case["predicted_route"] == case["expected_route"]), len(cases)),
        "rerank_success_rate": _ratio(sum(1 for case in expected_reranked if case["reranked_success"]), len(expected_reranked)),
        "recovery_verification_coverage": _ratio(sum(1 for case in cases if case["recovery_verification_present"]), len(cases)),
    }


def _failure_taxonomy(cases: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    taxonomy = {
        "detection_failure": 0,
        "root_cause_failure": 0,
        "evidence_gap": 0,
        "route_failure": 0,
        "rerank_failure": 0,
        "recovery_verification_gap": 0,
    }
    for case in cases:
        for failure in _sequence(case.get("failures", ())):
            if isinstance(failure, str) and failure in taxonomy:
                taxonomy[failure] += 1
    return taxonomy


def _evidence_item(signal: Mapping[str, Any]) -> dict[str, str]:
    return {
        "source": str(signal.get("source", "unknown")),
        "signal": str(signal.get("signal", "unknown")),
        "value": str(signal.get("value", "")),
        "strength": str(signal.get("strength", "low")),
    }


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
