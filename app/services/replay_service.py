"""P7 deterministic incident replay harness."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db import Base
from app.models import action as _action_model  # noqa: F401
from app.models import audit as _audit_model  # noqa: F401
from app.models import evidence as _evidence_model  # noqa: F401
from app.models import identity as _identity_model  # noqa: F401
from app.models import incident as _incident_model  # noqa: F401
from app.models import policy as _policy_model  # noqa: F401
from app.models import secret as _secret_model  # noqa: F401
from app.models import timeline as _timeline_model  # noqa: F401
from app.models import workflow as _workflow_model  # noqa: F401
from app.schemas.incidents import MockAlertRequest
from app.services.confidence_calibration import calibrate_replay_results
from app.services.incident_service import create_and_investigate, decide_action
from app.services.report_service import render_incident_report

DEFAULT_REPLAY_DIR = Path("evals/replay")


@dataclass(frozen=True)
class ReplayScenario:
    name: str
    path: Path
    input_alert: dict[str, Any]
    expected: dict[str, Any]
    category: str
    adversarial: bool
    safety_focus: tuple[str, ...]


def load_replay_scenarios(replay_dir: Path = DEFAULT_REPLAY_DIR, scenarios: Iterable[str] | None = None) -> list[ReplayScenario]:
    selected = set(scenarios or [])
    paths = sorted(path for path in replay_dir.rglob("*.json") if path.is_file())
    loaded: list[ReplayScenario] = []
    for path in paths:
        raw = json.loads(path.read_text(encoding="utf-8"))
        name = str(raw.get("scenario") or path.stem)
        if selected and name not in selected:
            continue
        loaded.append(
            ReplayScenario(
                name=name,
                path=path,
                input_alert=dict(raw["input_alert"]),
                expected=dict(raw["expected"]),
                category=str(raw.get("category", "uncategorized")),
                adversarial=bool(raw.get("adversarial", "adversarial" in path.parts)),
                safety_focus=tuple(str(item) for item in raw.get("safety_focus", [])),
            )
        )
    return loaded


def run_replay_scenarios(*, replay_dir: Path = DEFAULT_REPLAY_DIR, scenarios: Iterable[str] | None = None) -> dict[str, Any]:
    loaded = load_replay_scenarios(replay_dir, scenarios)
    results = [_run_one(scenario) for scenario in loaded]
    dangerous = [item for item in results if item.get("dangerous_action_attempt")]
    ambiguous = [item for item in results if item.get("ambiguous")]
    calibration = calibrate_replay_results(results)
    summary = {
        "total": len(results),
        "passed": sum(1 for item in results if item["passed"]),
        "failed": sum(1 for item in results if not item["passed"]),
        "adversarial_total": sum(1 for item in results if item["adversarial"]),
        "blocked_dangerous_actions": {
            "total": len(dangerous),
            "blocked": sum(1 for item in dangerous if item["policy_decision"] in {"DENY", "ESCALATE"}),
        },
        "ambiguous_escalations": {
            "total": len(ambiguous),
            "escalated": sum(1 for item in ambiguous if item["policy_decision"] == "ESCALATE" or item["actual_route"] == "escalated"),
        },
        "calibration": calibration.to_dict(),
        "results": results,
    }
    return summary


def render_replay_markdown(summary: Mapping[str, Any]) -> str:
    lines = [
        "# OpsCat P7 Replay Eval Report",
        "",
        "Deterministic local/mock replay scenarios evaluate reliability, adversarial safety, calibration, and fail-closed routing without credentials.",
        "",
        f"- Total: {summary['total']}",
        f"- Passed: {summary['passed']}",
        f"- Failed: {summary['failed']}",
        f"- Adversarial: {summary['adversarial_total']}",
        f"- Dangerous actions blocked: {summary['blocked_dangerous_actions']['blocked']}/{summary['blocked_dangerous_actions']['total']}",
        f"- Ambiguous escalations: {summary['ambiguous_escalations']['escalated']}/{summary['ambiguous_escalations']['total']}",
        "",
        "| Scenario | Category | Route | Policy | Confidence | Result |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for result in summary["results"]:
        lines.append(
            "| {scenario} | {category} | {route} | {policy} | {confidence:.2f} | {status} |".format(
                scenario=result["scenario"],
                category=result["category"],
                route=result["actual_route"],
                policy=result["policy_decision"],
                confidence=result["confidence"],
                status="PASS" if result["passed"] else "FAIL",
            )
        )
    failures = [item for item in summary["results"] if not item["passed"]]
    if failures:
        lines.extend(["", "## Failures"])
        for item in failures:
            failed = [name for name, check in item["checks"].items() if not check["ok"]]
            lines.append(f"- `{item['scenario']}` failed checks: {', '.join(failed)}")
    return "\n".join(lines) + "\n"


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
    dangerous = "unsafe_action" in scenario.safety_focus or "dangerous" in scenario.category
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
