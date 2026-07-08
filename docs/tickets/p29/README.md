# P29 — Telemetry-grounded Judgment Quality Evaluation

TDD sequence:

1. Add RED tests for the phase contract and release evidence.
2. Implement the smallest safe local/mock service and CLI surface.
3. Integrate a smoke check into `scripts/verify.sh`.
4. Run targeted checks and full verification.

Boundary: evaluation/local-mock by default, no default external model calls, no remediation execution, no production claims.
