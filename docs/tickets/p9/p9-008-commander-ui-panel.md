---
id: P9-008
title: Commander UI Panel
status: TODO
phase: P9
depends_on: [P9-001, P9-002, P9-003, P9-004, P9-005]
boundary: no-auth-local-mock
---

# P9-008 — Commander UI Panel

## Outcome

Expose commander stage, plan, readiness, graph summary, verification, learning, and next action in the UI.

## Non-Negotiable Boundaries

- Do not add OIDC, SSO, login, password, browser session, or CSRF auth work.
- Do not add real production mutation, Kubernetes/cloud/database execution, unrestricted shell execution, customer credentials, or hosted SaaS claims.
- Do not claim unattended production operation.
- Automatic actions must remain local/mock, allowlisted, policy-gated, simulated, audited, and reversible.

## Allowed / Likely Paths

- `app/api/operator.py`
- `tests/test_p9_commander_ui.py`
- `tests/test_operator_dashboard_e2e.py`

## Implementation Plan

1. Read `docs/operations/p9-ticket-roadmap.md` and this ticket.
2. Inspect current P8 services/tests before editing.
3. Write RED tests for the acceptance criteria.
4. Implement the smallest deterministic local/mock service/UI/eval/docs slice.
5. Run targeted tests and static checks.
6. Report exact evidence and changed files.

## Acceptance Focus

- commander stage
- response plan
- readiness
- evidence graph summary
- verification state
- learning signal

## TDD / Verification Plan

- RED: add/modify the ticket-specific tests first and verify they fail for the intended missing behavior.
- GREEN: implement minimal code/docs until the same targeted tests pass.
- Static checks: run `uv run --no-sync --extra dev ruff check app tests scripts` when code changes.
- Type checks: run `uv run --no-sync --extra dev mypy app tests scripts` for service/API changes.
- Final ticket evidence must mention no-auth/local-mock/no-production-mutation preservation.

## Completion Criteria

- Required tests pass.
- Output is deterministic and redacted where user/incident text appears.
- No external provider/network/shell execution is introduced unless already mocked and allowlisted.
- Ticket completion report lists code paths, tests, and verification evidence.
