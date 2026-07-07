---
id: P8-008
title: Operator Console Demo Polish
status: TODO
phase: P8
depends_on: [P8-002, P8-007]
boundary: no-auth-local-mock
---

# P8-008 — Operator Console Demo Polish

## Outcome

Make the P8 demo understandable as a portfolio-grade AI Incident Responder flow.

## Non-Negotiable Boundaries

- Do not add OIDC, SSO, login, password, browser session, or CSRF auth work.
- Do not add real production mutation, Kubernetes/cloud/database execution, unrestricted shell execution, customer credentials, or hosted SaaS claims.
- Automatic actions must remain local/mock, allowlisted, policy-gated, simulated, audited, and reversible.

## Allowed / Likely Paths

- `app/api/operator.py`
- `docs/operations/p8-demo-script.md`
- `scripts/demo.py`
- `tests/test_p8_demo.py`
- `tests/test_operator_dashboard_e2e.py`

## Implementation Plan

1. Add RED smoke/contract tests for demo flow: alert -> war room -> score -> runbook critique -> action gate -> report.
2. Polish UI copy to state local/mock boundary and avoid unattended production-operation claims.
3. Add demo script with exact commands and expected visible output.
4. Keep no-auth boundary explicit.

## TDD / Verification Plan

- `uv run --no-sync --extra dev pytest -q tests/test_p8_demo.py tests/test_operator_dashboard_e2e.py`
- `uv run --no-sync --extra dev python scripts/demo.py`

## Acceptance Criteria

- Required tests are written first and RED is observed before production code changes for this ticket.
- GREEN is observed on the same targeted test set after implementation.
- New output is deterministic and redacted.
- Safety boundaries above are preserved.
- Ticket completion report lists code paths, tests, and verification evidence.
