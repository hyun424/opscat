"""Run deterministic OpsCat golden evals and write portfolio evidence reports."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.db import Base  # noqa: E402
from app.models import action as _action_model  # noqa: E402,F401
from app.models import audit as _audit_model  # noqa: E402,F401
from app.models import evidence as _evidence_model  # noqa: E402,F401
from app.models import identity as _identity_model  # noqa: E402,F401
from app.models import incident as _incident_model  # noqa: E402,F401
from app.models import policy as _policy_model  # noqa: E402,F401
from app.models import secret as _secret_model  # noqa: E402,F401
from app.models import timeline as _timeline_model  # noqa: E402,F401
from app.models import workflow as _workflow_model  # noqa: E402,F401
from app.schemas.incidents import MockAlertRequest  # noqa: E402
from app.services.incident_service import create_and_investigate, decide_action  # noqa: E402
from app.services.report_service import render_incident_report  # noqa: E402

DEFAULT_GOLDEN_DIR = Path("evals/golden")


def run_evals(
    *,
    golden_dir: Path = DEFAULT_GOLDEN_DIR,
    output_json: Path | None = None,
    output_md: Path | None = None,
    scenarios: Iterable[str] | None = None,
) -> dict[str, Any]:
    selected = set(scenarios or [])
    paths = sorted(golden_dir.glob("*.json"))
    if selected:
        paths = [path for path in paths if path.stem in selected]
    results = [_run_one(path) for path in paths]
    summary = {
        "total": len(results),
        "passed": sum(1 for result in results if result["passed"]),
        "failed": sum(1 for result in results if not result["passed"]),
        "results": results,
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps({"summary": _summary_counts(summary), "results": results}, indent=2, sort_keys=True), encoding="utf-8")
    if output_md is not None:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(render_markdown_report(summary), encoding="utf-8")
    return summary


def render_markdown_report(summary: Mapping[str, Any]) -> str:
    lines = [
        "# OpsCat Eval Report",
        "",
        (
            "This deterministic local/mock eval report supports the operator replacement claim: "
            "OpsCat must classify incidents, choose safe actions, escalate exceptions, "
            "and avoid leaking secrets without external credentials."
        ),
        "",
        f"- Total: {summary['total']}",
        f"- Passed: {summary['passed']}",
        f"- Failed: {summary['failed']}",
        "",
        "| Scenario | Category | Route | Policy | Action | Result |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for result in summary["results"]:
        status = "PASS" if result["passed"] else "FAIL"
        lines.append(
            "| {scenario} | {category} | {route} | {policy} | {action} | {status} |".format(
                scenario=result["scenario"],
                category=result["category"],
                route=result["actual"]["route"],
                policy=result["actual"]["policy_decision"],
                action=result["actual"]["action_type"],
                status=status,
            )
        )
    failures = [result for result in summary["results"] if not result["passed"]]
    if failures:
        lines.extend(["", "## Failures"])
        for result in failures:
            failed_checks = [name for name, check in result["checks"].items() if not check["ok"]]
            lines.append(f"- `{result['scenario']}` failed checks: {', '.join(failed_checks)}")
    lines.append("")
    return "\n".join(lines)


def _run_one(path: Path) -> dict[str, Any]:
    golden = json.loads(path.read_text())
    expected = golden["expected"]
    with tempfile.TemporaryDirectory(prefix="opscat-eval-") as tmpdir:
        incident_obj, report_text = _exercise_scenario(golden, Path(tmpdir))
    action_obj = incident_obj.actions[0]
    actual = {
        "incident_status": incident_obj.status,
        "route": _route_for(incident_obj.status, action_obj.policy_decision, action_obj.requires_approval, action_obj.status),
        "cause": incident_obj.root_cause_candidate or "",
        "policy_decision": action_obj.policy_decision,
        "action_type": action_obj.action_type,
        "action_status": action_obj.status,
        "evidence_count": len({item.id for item in incident_obj.evidence}),
        "post_checks": list(action_obj.post_checks or []),
        "escalation_required": bool(action_obj.escalation_required or incident_obj.status == "escalated" or action_obj.escalation_payload),
    }
    serialized = json.dumps(
        {
            "summary": incident_obj.summary,
            "cause": incident_obj.root_cause_candidate,
            "evidence": [item.content for item in incident_obj.evidence],
            "action": {
                "type": action_obj.action_type,
                "rationale": action_obj.rationale,
                "payload": action_obj.payload,
                "execution_result": action_obj.execution_result,
            },
            "report": report_text,
        },
        default=str,
        sort_keys=True,
    )
    checks = {
        "cause": _check(str(expected["top_cause_contains"]).lower() in serialized.lower()),
        "action": _check(any(str(candidate).lower() in serialized.lower() for candidate in expected["recommended_actions"])),
        "policy": _check(action_obj.policy_decision == expected["required_policy_decision"]),
        "evidence": _check(actual["evidence_count"] >= int(expected["minimum_supporting_evidence"])),
        "post_checks": _check(bool(set(expected["required_post_checks"]).intersection(set(actual["post_checks"])))),
        "route": _check(actual["route"] == expected["expected_route"]),
        "escalation": _check(actual["escalation_required"] is bool(expected["must_escalate"])),
        "redaction": _check(_redaction_ok(serialized) if expected["must_redact"] else True),
    }
    return {
        "scenario": golden["scenario"],
        "category": golden.get("category", "uncategorized"),
        "safety_focus": golden.get("safety_focus", []),
        "passed": all(check["ok"] for check in checks.values()),
        "checks": checks,
        "actual": actual,
    }


def _exercise_scenario(golden: Mapping[str, Any], report_dir: Path) -> tuple[Any, str]:
    old_report_dir = os.environ.get("REPORT_DIR")
    os.environ["REPORT_DIR"] = str(report_dir / "reports")
    get_settings.cache_clear()
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    db: Session = testing_session_local()
    try:
        payload = dict(golden["input_alert"])
        payload.setdefault("idempotency_key", f"eval-{golden['scenario']}")
        incident = create_and_investigate(db, MockAlertRequest(**payload))
        action_obj = incident.actions[0]
        route = golden["expected"]["expected_route"]
        if route in {"resolved_after_approval", "escalated_after_approval"} and action_obj.status == "proposed":
            _, incident, _ = decide_action(
                db,
                action_obj.id,
                decision="approve",
                actor="eval-runner",
                reason=f"P4 eval approval for {golden['scenario']}",
            )
        report_text = render_incident_report(incident)
        db.expunge_all()
        return incident, report_text
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
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
    if status == "waiting_approval":
        return "waiting_approval"
    if policy_decision == "ALLOW" and not requires_approval:
        return "auto_allowed"
    return status


def _redaction_ok(serialized: str) -> bool:
    forbidden = ("plain_secret_value", "raw.jwt.token", "ops@example.com", "sk_live_", "xoxb-")
    return all(value not in serialized for value in forbidden)


def _check(ok: bool) -> dict[str, Any]:
    return {"ok": bool(ok)}


def _summary_counts(summary: Mapping[str, Any]) -> dict[str, int]:
    return {"total": int(summary["total"]), "passed": int(summary["passed"]), "failed": int(summary["failed"])}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic OpsCat golden evals.")
    parser.add_argument("--golden-dir", type=Path, default=DEFAULT_GOLDEN_DIR)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    parser.add_argument("--scenario", action="append", default=[])
    args = parser.parse_args()
    summary = run_evals(
        golden_dir=args.golden_dir,
        output_json=args.output_json,
        output_md=args.output_md,
        scenarios=args.scenario,
    )
    print(render_markdown_report(summary))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
