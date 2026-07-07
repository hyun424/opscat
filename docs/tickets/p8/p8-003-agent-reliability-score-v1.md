---
id: P8-003
title: Agent Reliability Score v1
status: TODO
phase: P8
depends_on: [P8-001]
boundary: no-auth-local-mock
---

# P8-003 — Agent Reliability Score v1

## Outcome

Create an explainable reliability score that appears in the war room and cannot bypass hard safety policy.

## Non-Negotiable Boundaries

- Do not add OIDC, SSO, login, password, browser session, or CSRF auth work.
- Do not add real production mutation, Kubernetes/cloud/database execution, unrestricted shell execution, customer credentials, or hosted SaaS claims.
- Automatic actions must remain local/mock, allowlisted, policy-gated, simulated, audited, and reversible.

## Allowed / Likely Paths

- `app/services/agent_reliability_score.py`
- `app/services/reliability_dashboard.py`
- `app/services/confidence_calibration.py`
- `app/services/replay_service.py`
- `app/services/war_room_service.py`
- `tests/test_agent_reliability_score.py`

## Implementation Plan

1. Add RED tests for score decomposition, bands, high-confidence dangerous action still blocked, missing evidence penalty, stale memory penalty, and simulation/post-check effects.
2. Implement deterministic component scoring with explainable breakdown.
3. Wire score into war room output and reliability dashboard-compatible structures.
4. Enforce invariant: prohibited/unknown blast radius blocks regardless of score.

## TDD / Verification Plan

- `uv run --no-sync --extra dev pytest -q tests/test_agent_reliability_score.py tests/test_war_room_service.py`
- `uv run --no-sync --extra dev mypy app tests scripts`

## Acceptance Criteria

- Required tests are written first and RED is observed before production code changes for this ticket.
- GREEN is observed on the same targeted test set after implementation.
- New output is deterministic and redacted.
- Safety boundaries above are preserved.
- Ticket completion report lists code paths, tests, and verification evidence.
