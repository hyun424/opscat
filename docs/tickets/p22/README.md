# P22 — Night-shift Runtime Drill and SLA Scoring

Implement P22 by TDD:

1. Add RED tests for drill scenario loading, runner, scoring, CLI, and release evidence.
2. Implement minimal local/mock drill service and CLI.
3. Integrate smoke into `scripts/verify.sh`.
4. Run targeted tests, static checks, related regression, and full verification.
5. Commit RED, GREEN, and evidence checkpoints.

Boundary: local/mock only; no auth; no production mutation; no remediation execution.
