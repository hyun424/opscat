# P28 — Read-only Polling Runtime

TDD sequence:

1. Add RED tests for the phase contract and release evidence.
2. Implement the smallest safe local/mock service and CLI surface.
3. Integrate a smoke check into `scripts/verify.sh`.
4. Run targeted checks and full verification.

Boundary: read-only polling only, fixture/local transport by default, no production mutation, no remediation execution, no auth feature.
