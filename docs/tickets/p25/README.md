# P25 — Proactive Signal Corpus Expansion and Calibration

TDD sequence:

1. Add RED tests for 100+ proactive fixtures, expected outcome metadata, calibration evaluator, CLI, and release evidence.
2. Expand fixtures and implement calibration service/reporting.
3. Integrate smoke into `scripts/verify.sh`.
4. Run targeted tests, static checks, compatibility checks, and full verification.
5. Commit RED, GREEN, and evidence checkpoints.

Boundary: local/mock only; no auth; no production mutation; no remediation execution.
