---
id: P8-004
title: Runbook Critic and Improvement Suggestions
status: TODO
phase: P8
depends_on: [P8-001]
boundary: no-auth-local-mock
---

# P8-004 — Runbook Critic and Improvement Suggestions

## Outcome

Critique runbook fit before action and suggest safer local text improvements.

## Non-Negotiable Boundaries

- Do not add OIDC, SSO, login, password, browser session, or CSRF auth work.
- Do not add real production mutation, Kubernetes/cloud/database execution, unrestricted shell execution, customer credentials, or hosted SaaS claims.
- Automatic actions must remain local/mock, allowlisted, policy-gated, simulated, audited, and reversible.

## Allowed / Likely Paths

- `app/services/runbook_critic.py`
- `app/services/runbook_service.py`
- `app/services/incident_memory.py`
- `app/services/self_critique_service.py`
- `app/services/war_room_service.py`
- `tests/test_runbook_critic.py`

## Implementation Plan

1. Add RED tests for `good_fit`, `weak_fit`, `unsafe`, and `insufficient_evidence`.
2. Cover successful prior, failed prior, missing evidence, protected service, and prohibited action.
3. Implement critic with deterministic reasons and no external runbook mutation.
4. Surface critique and suggestions in war room.

## TDD / Verification Plan

- `uv run --no-sync --extra dev pytest -q tests/test_runbook_critic.py tests/test_war_room_service.py`
- `uv run --no-sync --extra dev ruff check app tests scripts`

## Acceptance Criteria

- Required tests are written first and RED is observed before production code changes for this ticket.
- GREEN is observed on the same targeted test set after implementation.
- New output is deterministic and redacted.
- Safety boundaries above are preserved.
- Ticket completion report lists code paths, tests, and verification evidence.
