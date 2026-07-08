# P31 — End-to-End Operator Replacement Drill

TDD sequence:

1. Add RED tests for E2E drill contract and release evidence.
2. Implement the smallest safe local/mock orchestrator and CLI.
3. Integrate smoke check into `scripts/verify.sh`.
4. Run targeted checks and full verification.

Boundary: local/mock by default, no auth, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no unattended production-operation claim.
