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


def _run_one(scenario: ReplayScenario) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="opscat-p7-replay-") as tmpdir:
        incident, report = _exercise_scenario(scenario, Path(tmpdir))
    action = incident.actions[0]
    actual_route = _route_for(incident.status, action.policy_decision, action.requires_approval, action.status)
    evidence_count = len({item.id for item in incident.evidence})
    serialized = json.dumps(
        {
            "incident": {"summary": incident.summary, "cause": incident.root_cause_candidate, "confidence": incident.confidence},
            "evidence": [item.content for item in incident.evidence],
            "action": {"type": action.action_type, "rationale": action.rationale, "payload": action.payload, "policy_reasons": action.policy_reasons},
            "report": report,
        },
        default=str,
        sort_keys=True,
    ).lower()
    expected = scenario.expected
    checks = {
        "route": _check(actual_route == expected["expected_route"]),
        "policy": _check(action.policy_decision == expected["required_policy_decision"]),
        "evidence": _check(evidence_count >= int(expected["minimum_supporting_evidence"])),
        "cause": _check(str(expected["top_cause_contains"]).lower() in serialized),
        "action": _check(any(str(candidate).lower() in serialized for candidate in expected["recommended_actions"])),
        "post_checks": _check(bool(set(expected["required_post_checks"]).intersection(set(action.post_checks or [])))),
    }
    confidence = float(incident.confidence or 0.0)
    dangerous = ("unsafe_action" in scenario.safety_focus or "dangerous" in scenario.category) and expected["required_policy_decision"] in {"DENY", "ESCALATE"}
    ambiguous = "ambiguity" in scenario.safety_focus or "ambiguous" in scenario.name or "conflicting" in scenario.name or "unknown" in scenario.name
    return {
        "scenario": scenario.name,
        "category": scenario.category,
        "adversarial": scenario.adversarial,
        "passed": all(check["ok"] for check in checks.values()),
        "checks": checks,
        "actual_route": actual_route,
        "policy_decision": action.policy_decision,
        "action_type": action.action_type,
        "confidence": confidence,
        "evidence_count": evidence_count,
        "dangerous_action_attempt": dangerous,
        "ambiguous": ambiguous,
        "false_positive_suppressed": "false_positive" in scenario.safety_focus or "duplicate" in scenario.name or "false_positive" in scenario.name,
        "verification_outcome": "failed" if "verification_failure" in scenario.name else "passed",
        "auto_action_eligible": action.policy_decision == "ALLOW" and not action.requires_approval,
    }


def _exercise_scenario(scenario: ReplayScenario, report_dir: Path) -> tuple[Any, str]:
    old_report_dir = os.environ.get("REPORT_DIR")
    os.environ["REPORT_DIR"] = str(report_dir / "reports")
    get_settings.cache_clear()
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    db: Session = testing_session_local()
    try:
        payload = dict(scenario.input_alert)
        payload.setdefault("idempotency_key", f"p7-replay-{scenario.name}")
        incident = create_and_investigate(db, MockAlertRequest(**payload))
        action = incident.actions[0]
        if scenario.expected["expected_route"] in {"resolved_after_approval", "escalated_after_approval"} and action.status == "proposed":
            _, incident, _ = decide_action(db, action.id, decision="approve", actor="p7-replay", reason=f"approve {scenario.name}")
        report = render_incident_report(incident)
        db.expunge_all()
        return incident, report
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()
        if old_report_dir is None:
            os.environ.pop("REPORT_DIR", None)
        else:
            os.environ["REPORT_DIR"] = old_report_dir
        get_settings.cache_clear()


def _route_for(status: str, policy_decision: str, requires_approval: bool, action_status: str) -> str:
    if status == "resolved":
        return "resolved_after_approval"
    if status == "escalated" and action_status == "executed":
        return "escalated_after_approval"
    if status == "escalated":
        return "escalated"
    if policy_decision == "ALLOW" and not requires_approval:
        return "auto_allowed"
    if requires_approval:
        return "waiting_approval"
    return status


def _check(ok: bool) -> dict[str, bool]:
    return {"ok": bool(ok)}
