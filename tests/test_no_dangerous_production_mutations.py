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
    def test_production_write_is_denied_even_when_approved(self) -> None:
        request = ActionRequest(
            name="restart-payment-worker",
            environment="production",
            risk_level=RiskLevel.MEDIUM,
            mutation_kind=MutationKind.EXTERNAL_WRITE,
            requires_approval=True,
            approved=True,
            post_checks=("verify error rate recovered",),
        )

        result = evaluate_action_policy(request)

        self.assertIs(result.decision, PolicyDecision.DENY)
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

                self.assertIs(result.decision, PolicyDecision.DENY)
                self.assertTrue(
                    any(mutation_kind.value in reason for reason in result.reasons)
                )

    def test_approval_gated_non_production_write_requires_approval(self) -> None:
        request = ActionRequest(
            name="create-rollback-pr",
            environment="staging",
            risk_level=RiskLevel.MEDIUM,
            mutation_kind=MutationKind.EXTERNAL_WRITE,
            requires_approval=True,
            approved=False,
            post_checks=("confirm PR is draft only",),
        )

        result = evaluate_action_policy(request)

        self.assertIs(result.decision, PolicyDecision.REQUIRE_APPROVAL)
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

        self.assertIs(result.decision, PolicyDecision.ALLOW)
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

        self.assertIs(result.decision, PolicyDecision.DENY)
        self.assertIn("medium/high risk actions require post-checks", result.reasons)

    def test_production_environment_aliases_are_detected(self) -> None:
        self.assertTrue(is_production_environment("prod"))
        self.assertTrue(is_production_environment(" production "))
        self.assertTrue(is_production_environment("live"))
        self.assertFalse(is_production_environment("staging"))


if __name__ == "__main__":
    unittest.main()
