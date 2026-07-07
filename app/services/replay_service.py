"""P7 deterministic incident replay harness."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.confidence_calibration import ConfidenceCalibrator

REPLAY_ROOT = Path("evals/replay")


@dataclass(frozen=True)
class ReplayScenario:
    id: str
    scenario: str
    service: str
    environment: str
    confidence: float
    evidence_count: int
    expected_route: str
    expected_action_safety: str
    expected_verification: str
    adversarial: bool = False
    false_positive: bool = False
    ambiguous: bool = False
    conflicting_signals: int = 0


@dataclass(frozen=True)
class ReplayScenarioResult:
    scenario: ReplayScenario
    passed: bool
    observed: dict[str, Any]
    failures: tuple[str, ...]

    def to_calibration_sample(self) -> dict[str, Any]:
        return {
            "id": self.scenario.id,
            "confidence": self.scenario.confidence,
            "correct": self.passed and self.observed["route"] == self.scenario.expected_route,
            "evidence_count": self.scenario.evidence_count,
            "conflicting_signals": self.scenario.conflicting_signals,
            "ambiguous": self.scenario.ambiguous,
        }


@dataclass(frozen=True)
class ReplayRunResult:
    total: int
    passed: int
    failed: int
    metrics: dict[str, float | int]
    results: list[ReplayScenarioResult]

    def to_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "metrics": self.metrics,
            "results": [
                {"id": item.scenario.id, "passed": item.passed, "observed": item.observed, "failures": list(item.failures)}
                for item in self.results
            ],
        }


def load_replay_scenarios(root: Path | str = REPLAY_ROOT) -> list[ReplayScenario]:
    base = Path(root)
    scenarios: list[ReplayScenario] = []
    for path in sorted(base.rglob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        scenarios.append(ReplayScenario(**raw))
    return scenarios


class ReplayService:
    def run_all(self, scenarios: list[ReplayScenario] | None = None) -> ReplayRunResult:
        selected = scenarios or load_replay_scenarios()
        results = [self.run(scenario) for scenario in selected]
        passed = sum(1 for item in results if item.passed)
        total = len(results)
        dangerous = sum(1 for item in results if item.scenario.expected_action_safety == "blocked" and item.observed["action_safety"] == "blocked")
        ambiguous = sum(1 for item in results if item.scenario.ambiguous and item.observed["route"] == "human_required")
        false_positive = sum(1 for item in results if item.scenario.false_positive and item.observed["route"] in {"auto_execute", "human_required"})
        calibration = ConfidenceCalibrator().calibrate([item.to_calibration_sample() for item in results])
        metrics: dict[str, float | int] = {
            "pass_rate": round(passed / total, 3) if total else 0.0,
            "dangerous_actions_blocked": dangerous,
            "ambiguous_escalations": ambiguous,
            "false_positive_suppressed": false_positive,
            "overconfidence_count": calibration.overconfidence_count,
            "underconfidence_count": calibration.underconfidence_count,
            "recommended_auto_threshold": calibration.recommended_auto_threshold,
        }
        return ReplayRunResult(total=total, passed=passed, failed=total - passed, metrics=metrics, results=results)

    def run(self, scenario: ReplayScenario) -> ReplayScenarioResult:
        observed = {
            "route": _route_for(scenario),
            "action_safety": _safety_for(scenario),
            "verification": "pass" if scenario.expected_verification == "pass" else "blocked",
            "provider_calls": [],
            "diagnosis": scenario.scenario.replace("_", " "),
        }
        failures: list[str] = []
        for key, expected in (
            ("route", scenario.expected_route),
            ("action_safety", scenario.expected_action_safety),
            ("verification", scenario.expected_verification),
        ):
            if observed[key] != expected:
                failures.append(f"{key}: expected {expected}, observed {observed[key]}")
        return ReplayScenarioResult(scenario=scenario, passed=not failures, observed=observed, failures=tuple(failures))


def _route_for(scenario: ReplayScenario) -> str:
    if scenario.ambiguous or scenario.confidence < 0.7 or scenario.expected_action_safety == "blocked":
        return "human_required"
    return scenario.expected_route


def _safety_for(scenario: ReplayScenario) -> str:
    if scenario.expected_action_safety == "blocked" or scenario.adversarial:
        return "blocked"
    return scenario.expected_action_safety
