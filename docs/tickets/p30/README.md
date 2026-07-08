# P30 — Controlled Auto-remediation Policy and Simulation

TDD sequence:

1. Add RED tests for the phase contract and release evidence.
2. Implement the smallest safe local/mock service and CLI surface.
3. Integrate a smoke check into `scripts/verify.sh`.
4. Run targeted checks and full verification.

Boundary: simulation/local-mock by default, no production mutation, no auth, no unrestricted shell, no unattended production-operation claim.
