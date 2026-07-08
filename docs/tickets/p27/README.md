# P27 — Connector Readiness and Permission Contract

TDD sequence:

1. Add RED tests for the phase contract and release evidence.
2. Implement the smallest safe local/mock service and CLI surface.
3. Integrate a smoke check into `scripts/verify.sh`.
4. Run targeted checks and full verification.

Boundary: no auth, no production mutation, no remediation execution, no live writes, no default external model/API calls, no unattended production-operation claim.
