from unittest import TestCase

from app.models.action import ActionRequest, ActionStatus, PolicyDecision, RiskLevel
from app.services.action_service import ActionService
from app.services.policy_engine import PolicyContext, default_capabilities


class PolicyActionTests(TestCase):
    def test_read_only_context_action_is_allowed(self) -> None:
        svc = ActionService()
        record = svc.propose(
            ActionRequest(action_type="mock.get_error_context", target="payment-api"),
            PolicyContext(capabilities=default_capabilities(), environment="local"),
        )

        self.assertEqual(record.evaluation.decision, PolicyDecision.ALLOW)
        self.assertEqual(record.evaluation.risk_level, RiskLevel.READ_ONLY)
        self.assertFalse(record.evaluation.requires_approval)

    def test_ticket_creation_requires_approval_then_executes_mock(self) -> None:
        svc = ActionService()
        context = PolicyContext(
            capabilities=default_capabilities({"mock:tickets:write"}),
            environment="local",
        )
        record = svc.propose(
            ActionRequest(
                action_type="mock.create_incident_ticket",
                target="payment-api",
                incident_id="inc-123",
                payload={"title": "Payment API error spike"},
            ),
            context,
        )

        self.assertEqual(record.evaluation.decision, PolicyDecision.REQUIRE_APPROVAL)
        blocked = svc.execute(record.id, context)
        self.assertEqual(blocked.status, ActionStatus.FAILED)
        self.assertIn("requires approval", blocked.message)

        svc.approve(record.id, actor="oncall@example.com", reason="safe mock ticket")
        result = svc.execute(record.id, context)

        self.assertEqual(result.status, ActionStatus.EXECUTED)
        self.assertTrue(result.output["ticket_id"].startswith("OPSCAT-"))
        self.assertTrue(result.verification["ticket_id_recorded"])

    def test_production_and_shell_actions_are_denied(self) -> None:
        svc = ActionService()
        context = PolicyContext(
            capabilities=default_capabilities({"mock:pull_requests:write"}),
            environment="production",
        )

        prod = svc.propose(
            ActionRequest(
                action_type="production.rollback",
                target="payment-api",
                environment="production",
            ),
            context,
        )
        self.assertEqual(prod.evaluation.decision, PolicyDecision.DENY)
        self.assertEqual(prod.status, ActionStatus.DENIED)

        mock_pr = svc.propose(
            ActionRequest(
                action_type="mock.create_rollback_pr",
                target="payment-api",
                environment="production",
            ),
            context,
        )
        self.assertEqual(mock_pr.evaluation.decision, PolicyDecision.REQUIRE_APPROVAL)
        self.assertEqual(mock_pr.status, ActionStatus.PROPOSED)

        shell = svc.propose(
            ActionRequest(
                action_type="shell.execute",
                target="host",
                payload={"cmd": "rm -rf /"},
            )
        )
        self.assertEqual(shell.evaluation.decision, PolicyDecision.DENY)
        self.assertEqual(shell.evaluation.risk_level, RiskLevel.PROHIBITED)

    def test_night_autopilot_allows_only_low_risk_allowlisted_actions(self) -> None:
        svc = ActionService()
        context = PolicyContext(
            capabilities=default_capabilities({"mock:tickets:write"}),
            service="payment-api",
            environment="local",
            night_autopilot=True,
        )

        report = svc.propose(
            ActionRequest(
                action_type="report.generate",
                target="incident-report",
                incident_id="inc-123",
                payload={"evidence_ids": ["ev-1", "ev-2"]},
            ),
            context,
        )
        self.assertEqual(report.evaluation.decision, PolicyDecision.ALLOW)
        self.assertEqual(svc.execute(report.id, context).status, ActionStatus.EXECUTED)

        ticket = svc.propose(
            ActionRequest(action_type="mock.create_incident_ticket", target="payment-api"),
            context,
        )
        self.assertEqual(ticket.evaluation.decision, PolicyDecision.REQUIRE_APPROVAL)
