import unittest

from opscat.safety import (
    ActionRequest,
    MutationKind,
    PolicyDecision,
    RiskLevel,
    evaluate_action_policy,
    is_production_environment,
)


class NoDangerousProductionMutationPolicyTest(unittest.TestCase):
    def test_production_mutation_is_denied_even_when_approved(self) -> None:
        request = ActionRequest(
            name="restart-payment-worker",
            environment="production",
            risk_level=RiskLevel.HIGH,
            mutation_kind=MutationKind.PRODUCTION_MUTATION,
            requires_approval=True,
            approved=True,
            post_checks=("verify error rate recovered",),
        )

        result = evaluate_action_policy(request)

        self.assertEqual(result.decision.value, PolicyDecision.DENY.value)
        self.assertFalse(result.allowed)
        self.assertIn("production mutations are disabled in the MVP", result.reasons)

    def test_explicitly_prohibited_mutations_fail_closed(self) -> None:
        prohibited_cases = [
            MutationKind.PRODUCTION_MUTATION,
            MutationKind.DATABASE_MUTATION,
            MutationKind.INFRASTRUCTURE_MUTATION,
            MutationKind.DATA_DELETION,
            MutationKind.SECRET_ACCESS,
            MutationKind.ARBITRARY_SHELL,
        ]

        for mutation_kind in prohibited_cases:
            with self.subTest(mutation_kind=mutation_kind):
                request = ActionRequest(
                    name=f"dangerous-{mutation_kind.value}",
                    environment="staging",
                    risk_level=RiskLevel.LOW,
                    mutation_kind=mutation_kind,
                    approved=True,
                    post_checks=("verify no unsafe effect",),
                )

                result = evaluate_action_policy(request)

                self.assertEqual(result.decision.value, PolicyDecision.DENY.value)
                self.assertTrue(
                    any(mutation_kind.value in reason for reason in result.reasons)
                )

    def test_approval_gated_external_write_requires_approval(self) -> None:
        request = ActionRequest(
            name="create-rollback-pr",
            environment="production",
            risk_level=RiskLevel.MEDIUM,
            mutation_kind=MutationKind.EXTERNAL_WRITE,
            requires_approval=True,
            approved=False,
            post_checks=("confirm PR is draft only",),
        )

        result = evaluate_action_policy(request)

        self.assertEqual(result.decision.value, PolicyDecision.REQUIRE_APPROVAL.value)
        self.assertFalse(result.allowed)

    def test_safe_read_only_action_is_allowed_in_production(self) -> None:
        request = ActionRequest(
            name="mock.get_error_context",
            environment="prod",
            risk_level=RiskLevel.READ_ONLY,
            mutation_kind=MutationKind.READ_ONLY,
            requires_approval=False,
        )

        result = evaluate_action_policy(request)

        self.assertEqual(result.decision.value, PolicyDecision.ALLOW.value)
        self.assertTrue(result.allowed)

    def test_medium_risk_action_without_post_checks_is_denied(self) -> None:
        request = ActionRequest(
            name="create-incident-ticket",
            environment="dev",
            risk_level=RiskLevel.MEDIUM,
            mutation_kind=MutationKind.EXTERNAL_WRITE,
            requires_approval=False,
            post_checks=(),
        )

        result = evaluate_action_policy(request)

        self.assertEqual(result.decision.value, PolicyDecision.DENY.value)
        self.assertIn("medium/high risk actions require post-checks", result.reasons)

    def test_app_policy_denies_dangerous_action_aliases(self) -> None:
        from app.services.policy_engine import evaluate_policy

        for action_type in (
            "production_rollback",
            "database_mutation",
            "arbitrary_shell",
            "cloud_delete",
            "secret_access",
        ):
            with self.subTest(action_type=action_type):
                result = evaluate_policy(
                    {
                        "action_type": action_type,
                        "environment": "production",
                        "payload": {"service": "payment-api"},
                        "approved": True,
                    }
                )
                self.assertEqual(result.decision.value, PolicyDecision.DENY.value)

    def test_app_policy_keeps_mock_pr_approval_gated(self) -> None:
        from app.services.policy_engine import evaluate_policy

        result = evaluate_policy(
            {
                "action_type": "mock.create_rollback_pr",
                "environment": "production",
                "payload": {"service": "payment-api", "candidate_deploy": "deploy-42"},
                "approved": False,
            }
        )

        self.assertEqual(result.decision.value, PolicyDecision.REQUIRE_APPROVAL.value)


    def test_production_environment_aliases_are_detected(self) -> None:
        self.assertTrue(is_production_environment("prod"))
        self.assertTrue(is_production_environment(" production "))
        self.assertTrue(is_production_environment("live"))
        self.assertFalse(is_production_environment("staging"))


if __name__ == "__main__":
    unittest.main()
