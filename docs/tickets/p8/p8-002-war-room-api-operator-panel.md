---
id: P8-002
title: War Room API and Operator Console Panel
status: TODO
phase: P8
depends_on: [P8-001, P8-003, P8-004, P8-005]
boundary: no-auth-local-mock
---

# P8-002 — War Room API and Operator Console Panel

## Outcome

Expose the war room via scoped API and operator-console UI panel.

## Non-Negotiable Boundaries

- Do not add OIDC, SSO, login, password, browser session, or CSRF auth work.
- Do not add real production mutation, Kubernetes/cloud/database execution, unrestricted shell execution, customer credentials, or hosted SaaS claims.
- Automatic actions must remain local/mock, allowlisted, policy-gated, simulated, audited, and reversible.

## Allowed / Likely Paths

- `app/api/incidents.py`
- `app/api/operator.py`
- `app/schemas/incidents.py`
- `tests/test_operator_dashboard.py`
- `tests/test_operator_dashboard_e2e.py`
- `tests/test_war_room_api.py`

## Implementation Plan

1. Add RED API tests for `GET /incidents/{id}/war-room`, workspace separation, redaction, and missing incident handling.
2. Add RED HTML/E2E contract tests for the War Room section.
3. Implement API schema/route and operator detail panel.
4. Show summary, impact, evidence, timeline, hypotheses, risk gates, next action, reliability score, runbook critique, human questions, and why not auto-execute.

## TDD / Verification Plan

- `uv run --no-sync --extra dev pytest -q tests/test_war_room_api.py tests/test_operator_dashboard.py tests/test_operator_dashboard_e2e.py`
- `uv run --no-sync --extra dev ruff check app tests scripts`

## Acceptance Criteria

- Required tests are written first and RED is observed before production code changes for this ticket.
- GREEN is observed on the same targeted test set after implementation.
- New output is deterministic and redacted.
- Safety boundaries above are preserved.
- Ticket completion report lists code paths, tests, and verification evidence.
