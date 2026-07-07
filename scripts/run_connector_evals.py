"""Run deterministic fake/local connector safety evals for P4 release evidence."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.connectors.base import ConnectorCallRequest, ConnectorCallResult, ConnectorCapability  # noqa: E402
from app.connectors.registry import ConnectorRegistry  # noqa: E402
from app.db import Base  # noqa: E402
from app.models import AuditEvent, ConnectorCallRecord, Incident  # noqa: E402
from app.models import action as _action_model  # noqa: E402,F401
from app.models import audit as _audit_model  # noqa: E402,F401
from app.models import evidence as _evidence_model  # noqa: E402,F401
from app.models import identity as _identity_model  # noqa: E402,F401
from app.models import incident as _incident_model  # noqa: E402,F401
from app.models import policy as _policy_model  # noqa: E402,F401
from app.models import secret as _secret_model  # noqa: E402,F401
from app.models import timeline as _timeline_model  # noqa: E402,F401
from app.models import workflow as _workflow_model  # noqa: E402,F401
from app.services.connector_service import ConnectorService  # noqa: E402
from app.services.identity_service import Principal, get_or_create_local_principal  # noqa: E402
from app.services.secret_service import LocalEncryptedSecretProvider  # noqa: E402

ScenarioResult = dict[str, Any]
ScenarioFn = Callable[[Session], ScenarioResult]


class _TimeoutConnector:
    connector_id = "eval.timeout"
    capabilities: Mapping[str, ConnectorCapability] = {
        "events.read": ConnectorCapability(
            name="events.read",
            description="Eval timeout connector.",
            read_only=True,
            required_role="viewer",
        )
    }

    def call(self, request: ConnectorCallRequest) -> ConnectorCallResult:
        raise TimeoutError("provider timed out")


class _MalformedConnector:
    connector_id = "eval.malformed"
    capabilities: Mapping[str, ConnectorCapability] = {
        "events.read": ConnectorCapability(
            name="events.read",
            description="Eval malformed connector.",
            read_only=True,
            required_role="viewer",
        )
    }

    def call(self, request: ConnectorCallRequest) -> Any:
        return {"ok": False, "error": "not a ConnectorCallResult"}


class _ContractViolationConnector:
    connector_id = "eval.contract"
    capabilities: Mapping[str, ConnectorCapability] = {
        "events.read": ConnectorCapability(
            name="events.read",
            description="Eval read-only contract violation connector.",
            read_only=True,
            required_role="viewer",
        )
    }

    def call(self, request: ConnectorCallRequest) -> ConnectorCallResult:
        return ConnectorCallResult(
            connector_id=self.connector_id,
            capability=request.capability,
            ok=True,
            read_only=False,
            output={"attempted_mutation": True},
            evidence_summary="Provider attempted a write while registered as read-only.",
        )


SCENARIOS: Mapping[str, ScenarioFn] = {
    "fake_read_success": lambda db: _fake_read_success(db),
    "missing_credential_failed_closed": lambda db: _missing_credential_failed_closed(db),
    "provider_timeout_escalates": lambda db: _provider_timeout_escalates(db),
    "malformed_result_escalates": lambda db: _malformed_result_escalates(db),
    "read_only_contract_violation_escalates": lambda db: _read_only_contract_violation_escalates(db),
    "idempotency_replay_no_duplicate_escalation": lambda db: _idempotency_replay_no_duplicate_escalation(db),
    "idempotency_conflict_fails_closed": lambda db: _idempotency_conflict_fails_closed(db),
}


def run_connector_evals(
    *,
    output_json: Path | None = None,
    output_md: Path | None = None,
    scenarios: list[str] | None = None,
) -> dict[str, Any]:
    selected = scenarios or list(SCENARIOS)
    unknown = sorted(set(selected) - set(SCENARIOS))
    if unknown:
        raise ValueError(f"unknown connector eval scenarios: {', '.join(unknown)}")
    results = [_run_isolated(name, SCENARIOS[name]) for name in selected]
    summary: dict[str, Any] = {
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
        "# OpsCat Connector Eval Report",
        "",
        (
            "This deterministic local/mock report proves connector calls fail closed, "
            "escalate when evidence collection breaks, preserve idempotency, and avoid real external mutations."
        ),
        "",
        f"- Total: {summary['total']}",
        f"- Passed: {summary['passed']}",
        f"- Failed: {summary['failed']}",
        "",
        "| Scenario | Category | Failure class | Escalated | Result |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result in cast(list[Mapping[str, Any]], summary["results"]):
        actual = cast(Mapping[str, Any], result["actual"])
        status = "PASS" if result["passed"] else "FAIL"
        lines.append(
            "| {scenario} | {category} | {failure_class} | {escalated} | {status} |".format(
                scenario=result["scenario"],
                category=result["category"],
                failure_class=actual.get("failure_class") or "none",
                escalated=actual.get("incident_status") == "escalated" or actual.get("human_escalation_count", 0) > 0,
                status=status,
            )
        )
    failures = [result for result in cast(list[Mapping[str, Any]], summary["results"]) if not result["passed"]]
    if failures:
        lines.extend(["", "## Failures"])
        for result in failures:
            failed_checks = [name for name, check in cast(Mapping[str, Mapping[str, Any]], result["checks"]).items() if not check["ok"]]
            lines.append(f"- `{result['scenario']}` failed checks: {', '.join(failed_checks)}")
    lines.append("")
    return "\n".join(lines)


def _run_isolated(name: str, scenario: ScenarioFn) -> ScenarioResult:
    engine = _new_engine()
    Base.metadata.create_all(bind=engine)
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    db: Session = testing_session_local()
    try:
        result = scenario(db)
        result["scenario"] = name
        result["passed"] = all(check["ok"] for check in result["checks"].values())
        return result
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _new_engine() -> Engine:
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _fake_read_success(db: Session) -> ScenarioResult:
    principal = _principal(db, role="viewer")
    result = ConnectorService().call(
        db,
        principal,
        ConnectorCallRequest(
            connector_id="fake.observability",
            capability="events.read",
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
            actor=principal.email,
            idempotency_key="eval-fake-read-success",
            payload={"service": "payment-api", "window": "10m"},
        ),
    )
    actual = {
        "ok": result.ok,
        "read_only": result.read_only,
        "failure_class": _latest_failure_class(db),
        "audit_types": _audit_types(db),
    }
    return _result(
        category="connector_success",
        actual=actual,
        checks={
            "ok": actual["ok"] is True,
            "read_only": actual["read_only"] is True,
            "audited": actual["audit_types"] == ["connector_call_requested", "connector_call_completed"],
        },
    )


def _missing_credential_failed_closed(db: Session) -> ScenarioResult:
    principal = _principal(db, role="viewer")
    incident = _incident(db)
    result = ConnectorService(secret_provider=LocalEncryptedSecretProvider(master_key="eval-master-key")).call(
        db,
        principal,
        ConnectorCallRequest(
            connector_id="sentry.readonly",
            capability="issues.read",
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
            actor=principal.email,
            incident_id=incident.id,
            idempotency_key="eval-missing-credential",
            payload={"project": "checkout-api"},
        ),
    )
    actual = _failure_actual(db, incident.id) | {"ok": result.ok, "error": result.error}
    return _result(
        category="connector_failure",
        actual=actual,
        checks={
            "failed_closed": result.ok is False and result.read_only is True,
            "missing_credential": result.error == "missing credential: sentry.token",
            "recorded_failure_class": actual["failure_class"] == "connector_failure",
            "escalated": actual["incident_status"] == "escalated",
        },
    )


def _provider_timeout_escalates(db: Session) -> ScenarioResult:
    return _custom_failure_eval(db, _TimeoutConnector(), scenario_key="eval-timeout", expected_error="connector provider failure: TimeoutError", expected_failure_class="connector_timeout")


def _malformed_result_escalates(db: Session) -> ScenarioResult:
    return _custom_failure_eval(db, _MalformedConnector(), scenario_key="eval-malformed", expected_error="connector provider failure: TypeError", expected_failure_class="connector_failure")


def _read_only_contract_violation_escalates(db: Session) -> ScenarioResult:
    return _custom_failure_eval(
        db,
        _ContractViolationConnector(),
        scenario_key="eval-contract-violation",
        expected_error="connector read-only contract violation",
        expected_failure_class="connector_contract_violation",
    )


def _idempotency_replay_no_duplicate_escalation(db: Session) -> ScenarioResult:
    principal = _principal(db, role="viewer")
    incident = _incident(db)
    service = ConnectorService(registry=_registry(_TimeoutConnector()))
    request = ConnectorCallRequest(
        connector_id="eval.timeout",
        capability="events.read",
        tenant_id=principal.tenant_id,
        workspace_id=principal.workspace_id,
        actor=principal.email,
        incident_id=incident.id,
        idempotency_key="eval-timeout-replay",
    )
    first = service.call(db, principal, request)
    second = service.call(db, principal, request)
    actual = _failure_actual(db, incident.id) | {
        "first_error": first.error,
        "second_error": second.error,
        "replayed": first == second,
        "audit_types": _audit_types(db),
    }
    return _result(
        category="idempotency",
        actual=actual,
        checks={
            "same_result": first == second,
            "single_failure_evidence": actual["failure_evidence_count"] == 1,
            "single_escalation": actual["human_escalation_count"] == 1,
            "replay_audited": "connector_call_replayed" in actual["audit_types"],
        },
    )


def _idempotency_conflict_fails_closed(db: Session) -> ScenarioResult:
    principal = _principal(db, role="viewer")
    service = ConnectorService()
    base = ConnectorCallRequest(
        connector_id="fake.observability",
        capability="events.read",
        tenant_id=principal.tenant_id,
        workspace_id=principal.workspace_id,
        actor=principal.email,
        idempotency_key="eval-conflict",
        payload={"service": "payment-api", "window": "5m"},
    )
    first = service.call(db, principal, base)
    second = service.call(
        db,
        principal,
        ConnectorCallRequest(
            connector_id="fake.observability",
            capability="events.read",
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
            actor=principal.email,
            idempotency_key="eval-conflict",
            payload={"service": "checkout-api", "window": "5m"},
        ),
    )
    actual = {
        "first_ok": first.ok,
        "second_ok": second.ok,
        "error": second.error,
        "failure_class": _latest_failure_class(db),
        "audit_types": _audit_types(db),
    }
    return _result(
        category="idempotency",
        actual=actual,
        checks={
            "first_completed": first.ok is True,
            "conflict_failed": second.ok is False and second.error == "conflicting idempotency key",
            "conflict_audited": actual["audit_types"] == ["connector_call_requested", "connector_call_completed", "connector_idempotency_conflict"],
        },
    )


def _custom_failure_eval(db: Session, connector: Any, *, scenario_key: str, expected_error: str, expected_failure_class: str) -> ScenarioResult:
    principal = _principal(db, role="viewer")
    incident = _incident(db)
    service = ConnectorService(registry=_registry(connector))
    result = service.call(
        db,
        principal,
        ConnectorCallRequest(
            connector_id=connector.connector_id,
            capability="events.read",
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
            actor=principal.email,
            incident_id=incident.id,
            idempotency_key=scenario_key,
        ),
    )
    actual = _failure_actual(db, incident.id) | {"ok": result.ok, "error": result.error}
    return _result(
        category="connector_failure",
        actual=actual,
        checks={
            "failed_closed": result.ok is False and result.read_only is True,
            "error": result.error == expected_error,
            "failure_class": actual["failure_class"] == expected_failure_class,
            "escalated": actual["incident_status"] == "escalated",
        },
    )


def _principal(db: Session, *, role: str) -> Principal:
    return get_or_create_local_principal(db, email=f"{role}@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role=role)


def _incident(db: Session) -> Incident:
    incident = Incident(
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        source="connector-eval",
        status="investigating",
        service="checkout-api",
        environment="staging",
        severity="high",
        alert_payload={"message": "connector eval regression token=secret owner@example.com"},
        summary="Connector eval regression token=summary-secret owner@example.com",
    )
    db.add(incident)
    db.flush()
    return incident


def _registry(connector: Any) -> ConnectorRegistry:
    registry = ConnectorRegistry()
    registry.register(connector)
    return registry


def _failure_actual(db: Session, incident_id: str) -> dict[str, Any]:
    db.flush()
    db.expire_all()
    incident = db.query(Incident).filter(Incident.id == incident_id).one()
    return {
        "incident_status": incident.status,
        "failure_class": _latest_failure_class(db),
        "failure_evidence_count": len([item for item in incident.evidence if item.type == "connector_failure"]),
        "human_escalation_count": len([event for event in incident.timeline if event.event_type == "human_escalation_required"]),
        "audit_types": _audit_types(db),
    }


def _latest_failure_class(db: Session) -> str | None:
    record = db.query(ConnectorCallRecord).order_by(ConnectorCallRecord.created_at.desc()).first()
    return cast(str | None, record.failure_class if record is not None else None)


def _audit_types(db: Session) -> list[str]:
    return [event.event_type for event in db.query(AuditEvent).order_by(AuditEvent.created_at).all()]


def _result(*, category: str, actual: Mapping[str, Any], checks: Mapping[str, bool]) -> ScenarioResult:
    return {
        "category": category,
        "actual": dict(actual),
        "checks": {name: {"ok": bool(ok)} for name, ok in checks.items()},
    }


def _summary_counts(summary: Mapping[str, Any]) -> dict[str, int]:
    return {"total": int(summary["total"]), "passed": int(summary["passed"]), "failed": int(summary["failed"])}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic OpsCat connector safety evals.")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    parser.add_argument("--scenario", action="append", default=[])
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="opscat-connector-eval-"):
        summary = run_connector_evals(output_json=args.output_json, output_md=args.output_md, scenarios=args.scenario or None)
    print(render_markdown_report(summary))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
