---
id: P8-005
title: Human Question Generator
status: TODO
phase: P8
depends_on: [P8-001, P8-003, P8-004]
boundary: no-auth-local-mock
---

# P8-005 — Human Question Generator

## Outcome

Generate concrete, safe human questions when evidence/policy gates block autonomy.

## Non-Negotiable Boundaries

- Do not add OIDC, SSO, login, password, browser session, or CSRF auth work.
- Do not add real production mutation, Kubernetes/cloud/database execution, unrestricted shell execution, customer credentials, or hosted SaaS claims.
- Automatic actions must remain local/mock, allowlisted, policy-gated, simulated, audited, and reversible.

## Allowed / Likely Paths

- `app/services/human_question_service.py`
- `app/services/self_critique_service.py`
- `app/services/war_room_service.py`
- `app/services/escalation.py`
- `tests/test_human_question_service.py`

## Implementation Plan

1. Add RED tests for low confidence, conflicting evidence, protected domain, failed simulation, and secret-seeking prevention.
2. Implement question objects with `question`, `why_it_matters`, `source_gate`, and `safe_to_ask`.
3. Wire generated questions into war room and escalation summaries.
4. Ensure questions never request credentials, tokens, or secrets.

## TDD / Verification Plan

- `uv run --no-sync --extra dev pytest -q tests/test_human_question_service.py tests/test_war_room_service.py`
- `uv run --no-sync --extra dev mypy app tests scripts`

## Acceptance Criteria

- Required tests are written first and RED is observed before production code changes for this ticket.
- GREEN is observed on the same targeted test set after implementation.
- New output is deterministic and redacted.
- Safety boundaries above are preserved.
- Ticket completion report lists code paths, tests, and verification evidence.
