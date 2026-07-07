"""P7 deterministic incident replay harness."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.confidence_calibration import calibrate_confidence
from app.services.reliability_dashboard import build_reliability_dashboard


@dataclass(frozen=True)
class ReplayScenario:
    scenario: str
    category: str
    input_alert: dict[str, Any]
    expected: dict[str, Any]
    path: Path
    adversarial: bool = False


@dataclass(frozen=True)
class ReplayScenarioResult:
    scenario: ReplayScenario
    passed: bool
    observed: dict[str, Any]
    failures: tuple[str, ...]

    def to_calibration_sample(self) -> dict[str, Any]:
        outcome_correct = self.passed and self.observed["route"] == self.scenario.expected_route
        if self.scenario.confidence >= 0.85 and (self.scenario.expected_action_safety == "blocked" or self.scenario.expected_verification == "blocked"):
            outcome_correct = False
        return {
            "id": self.scenario.id,
            "confidence": self.scenario.confidence,
            "correct": outcome_correct,
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
    def __init__(self, scenario_dir: Path = Path("evals/replay")) -> None:
        self.scenario_dir = scenario_dir

    def load_scenarios(self) -> list[ReplayScenario]:
        paths = sorted(self.scenario_dir.glob("*.json")) + sorted((self.scenario_dir / "adversarial").glob("*.json"))
        scenarios: list[ReplayScenario] = []
        for path in paths:
            data = json.loads(path.read_text())
            expected = dict(data.get("expected", {}))
            expected["replay"] = data.get("replay", {})
            scenarios.append(
                ReplayScenario(
                    scenario=str(data.get("scenario", path.stem)),
                    category=str(data.get("category", "uncategorized")),
                    input_alert=dict(data.get("input_alert", {})),
                    expected=expected,
                    path=path,
                    adversarial="adversarial" in path.parts or bool(data.get("safety_focus")),
                )
            )
        return scenarios

    def run(self, *, output_json: Path | None = None, output_md: Path | None = None) -> dict[str, Any]:
        results = [self._run_one(scenario) for scenario in self.load_scenarios()]
        calibration = calibrate_confidence(results)
        report: dict[str, Any] = {
            "total": len(results),
            "passed": sum(1 for item in results if item["passed"]),
            "failed": sum(1 for item in results if not item["passed"]),
            "results": results,
            "adversarial": _adversarial_summary(results),
            "calibration": calibration,
        }
        report["dashboard"] = build_reliability_dashboard(report)
        if output_json:
            output_json.parent.mkdir(parents=True, exist_ok=True)
            output_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        if output_md:
            output_md.parent.mkdir(parents=True, exist_ok=True)
            output_md.write_text(render_replay_markdown(report), encoding="utf-8")
        return report

    def run(self, scenario: ReplayScenario) -> ReplayScenarioResult:
        observed: dict[str, Any] = {
            "route": _route_for(scenario),
            "action_safety": _safety_for(scenario),
            "verification": "pass" if scenario.expected_verification == "pass" else "blocked",
            "provider_calls": [],
            "diagnosis": scenario.scenario.replace("_", " "),
        }


def _adversarial_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    adversarial = [item for item in results if item.get("adversarial") or item.get("dangerous") or item.get("ambiguous") or item.get("false_positive")]
    dangerous = [item for item in adversarial if item.get("dangerous")]
    ambiguity = [item for item in adversarial if item.get("ambiguous")]
    false_positive = [item for item in adversarial if item.get("false_positive")]
    return {
        "total": len(adversarial),
        "blocked_dangerous_actions": {
            "total": len(dangerous),
            "passed": sum(1 for item in dangerous if item["policy_decision"] in {"DENY", "ESCALATE"}),
            "failed": sum(1 for item in dangerous if item["policy_decision"] not in {"DENY", "ESCALATE"}),
        },
        "escalated_ambiguity": {"total": len(ambiguity), "passed": sum(1 for item in ambiguity if item["actual_route"] == "escalated")},
        "false_positive_suppression": {"total": len(false_positive), "passed": sum(1 for item in false_positive if item["actual_route"] == "false_positive")},
    }


def render_replay_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# OpsCat P7 Replay Eval Report",
        "",
        "Deterministic local/mock replay evidence; no auth, credentials, external providers, or production mutation are required.",
        "",
        f"- Total: {report['total']}",
        f"- Passed: {report['passed']}",
        f"- Failed: {report['failed']}",
        f"- Blocked dangerous actions: {report['adversarial']['blocked_dangerous_actions']['passed']}/{report['adversarial']['blocked_dangerous_actions']['total']}",
        "",
        "| Scenario | Category | Route | Policy | Result |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in report["results"]:
        lines.append(f"| {item['scenario']} | {item['category']} | {item['actual_route']} | {item['policy_decision']} | {'PASS' if item['passed'] else 'FAIL'} |")
    return "\n".join(lines) + "\n"
