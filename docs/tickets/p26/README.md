# P26 — Real Telemetry Adapter Contract

TDD sequence:

1. Add RED tests for telemetry contract, Prometheus/Datadog/Sentry fixtures, proactive TrendWindow conversion, CLI, and release evidence.
2. Add real-shaped local fixtures.
3. Implement adapter service and CLI.
4. Integrate smoke into `scripts/verify.sh`.
5. Run targeted checks and full verification.

Boundary: fixture/read-only only; no live API calls; no auth; no production mutation; no remediation execution.
