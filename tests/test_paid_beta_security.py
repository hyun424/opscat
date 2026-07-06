from datetime import UTC, datetime
from importlib.util import find_spec
from typing import Any
from unittest import TestCase, skipUnless

from app.models.action import ActionRequest
from app.services.action_service import ActionService
from app.services.policy_engine import PolicyContext, default_capabilities
from app.services.redaction import redact_text, redact_value


class PaidBetaSecurityUnitTests(TestCase):
    def test_redaction_removes_common_secret_and_pii_shapes(self) -> None:
        value = {
            "token": "ghp_real-token",
            "nested": ["Bearer sk-live-123", {"owner_email": "oncall@example.com"}],
            "safe": "keep-me",
        }

        redacted = redact_value(value)

        self.assertEqual(redacted["token"], "[REDACTED]")
        self.assertEqual(redacted["safe"], "keep-me")
        self.assertNotIn("sk-live-123", str(redacted))
        self.assertNotIn("oncall@example.com", str(redacted))
        self.assertIn("api_key=[REDACTED]", redact_text("api_key=abc123"))

    def test_action_audit_context_includes_tenant_workspace_and_checks(self) -> None:
        service = ActionService()
        record = service.propose(
            ActionRequest(
                action_type="mock.create_incident_ticket",
                target="payment-api",
                incident_id="inc-tenant-1",
                tenant_id="tenant-a",
                workspace_id="workspace-prod",
                payload={"title": "Payment API"},
            ),
            PolicyContext(
                capabilities=default_capabilities({"mock:tickets:write"}),
                tenant_id="tenant-a",
                workspace_id="workspace-prod",
            ),
        )

        serialized = service.serialize_record(record)

        self.assertEqual(serialized["action_request"]["tenant_id"], "tenant-a")
        self.assertEqual(serialized["action_request"]["workspace_id"], "workspace-prod")
        self.assertEqual(serialized["audit_context"]["tenant_id"], "tenant-a")
        self.assertEqual(serialized["audit_context"]["workspace_id"], "workspace-prod")
        self.assertEqual(serialized["audit_context"]["incident_id"], "inc-tenant-1")
        self.assertIn("ticket_id_recorded", serialized["audit_context"]["post_checks"])

    @skipUnless(find_spec("sqlalchemy") is not None, "SQLAlchemy unavailable in minimal policy env")
    def test_report_redacts_sensitive_evidence_payload_and_execution_output(self) -> None:
        from app.models import ActionProposal, Evidence, Incident, TimelineEvent
        from app.services.report_service import render_incident_report

        incident = Incident(
            id="inc-redact",
            source="mock",
            status="resolved",
            service="payment-api",
            environment="staging",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            severity="high",
            summary="Investigated by oncall@example.com",
            root_cause_candidate="Authorization Bearer sk-live-secret leaked in log",
            confidence=0.9,
        )
        incident.evidence = [
            Evidence(
                id="ev-secret",
                incident_id=incident.id,
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                type="log",
                source="mock",
                content="error token=secret-token for alice@example.com",
                evidence_metadata={},
            )
        ]
        incident.actions = [
            ActionProposal(
                id="act-secret",
                incident_id=incident.id,
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                action_type="mock.create_incident_ticket",
                target="payment-api",
                environment="staging",
                risk_level="medium",
                requires_approval=True,
                rationale="notify user bob@example.com",
                payload={"title": "incident", "api_key": "raw-key"},
                preconditions=[],
                post_checks=["ticket_id_recorded"],
                evidence_ids=["ev-secret"],
                policy_decision="REQUIRE_APPROVAL",
                policy_reasons=["approval required"],
                status="executed",
                execution_result={"ok": True, "output": {"token": "runtime-token"}},
            )
        ]
        incident.timeline = [
            TimelineEvent(
                id="tl-secret",
                incident_id=incident.id,
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                timestamp=datetime.now(UTC),
                actor="agent",
                event_type="note",
                content="password=hunter2",
                event_metadata={},
            )
        ]

        report = render_incident_report(incident)

        self.assertIn("tenant-a", report)
        self.assertIn("workspace-a", report)
        for forbidden in [
            "oncall@example.com",
            "sk-live-secret",
            "secret-token",
            "alice@example.com",
            "bob@example.com",
            "raw-key",
            "runtime-token",
            "hunter2",
        ]:
            self.assertNotIn(forbidden, report)
        self.assertIn("[REDACTED]", report)


def test_mock_alert_carries_tenant_boundary_to_incident_artifacts(client: Any) -> None:
    response = client.post(
        "/webhooks/alerts/mock",
        headers={
            "X-OpsCat-Actor": "operator@example.com",
            "X-OpsCat-Tenant": "tenant-paid-beta",
            "X-OpsCat-Workspace": "workspace-oncall",
            "X-OpsCat-Role": "operator",
        },
        json={
            "scenario": "payment_api_deploy_regression",
            "tenant_id": "tenant-paid-beta",
            "workspace_id": "workspace-oncall",
        },
    )

    assert response.status_code == 201, response.text
    incident = response.json()

    assert incident["tenant_id"] == "tenant-paid-beta"
    assert incident["workspace_id"] == "workspace-oncall"
    assert incident["evidence"]
    assert incident["actions"]
    assert incident["timeline"]
    assert {item["tenant_id"] for item in incident["evidence"]} == {"tenant-paid-beta"}
    assert {item["workspace_id"] for item in incident["evidence"]} == {"workspace-oncall"}
    assert {item["tenant_id"] for item in incident["actions"]} == {"tenant-paid-beta"}
    assert {item["workspace_id"] for item in incident["actions"]} == {"workspace-oncall"}
    assert {item["tenant_id"] for item in incident["timeline"]} == {"tenant-paid-beta"}
    assert {item["workspace_id"] for item in incident["timeline"]} == {"workspace-oncall"}
