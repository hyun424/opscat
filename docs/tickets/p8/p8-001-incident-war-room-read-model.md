---
id: P8-001
title: Incident War Room Read Model
status: TODO
phase: P8
depends_on: []
boundary: no-auth-local-mock
---

# P8-001 — Incident War Room Read Model

## Outcome

Build a deterministic war room read model for a single incident.

## Non-Negotiable Boundaries

- Do not add OIDC, SSO, login, password, browser session, or CSRF auth work.
- Do not add real production mutation, Kubernetes/cloud/database execution, unrestricted shell execution, customer credentials, or hosted SaaS claims.
- Automatic actions must remain local/mock, allowlisted, policy-gated, simulated, audited, and reversible.

## Allowed / Likely Paths

- `app/services/war_room_service.py`
- `app/services/incident_service.py`
- `app/services/decision_trace_service.py`
- `app/services/report_service.py`
- `app/services/incident_memory.py`
- `tests/test_war_room_service.py`

## Implementation Plan

1. Add RED unit/integration tests for war room shape, redaction, deterministic ordering, and mock-alert to investigated-incident assembly.
2. Implement `WarRoomService` with data classes/serializable dict output.
3. Include status, impact, timeline, current hypothesis, top 3 root-cause candidates, evidence, missing evidence, proposed action, policy decision, blast-radius, simulation, memory matches, reliability gates, and human questions placeholders.
4. Ensure every text field passes existing redaction.
5. Keep provider/network/shell calls out of the read model.

## TDD / Verification Plan

- `uv run --no-sync --extra dev pytest -q tests/test_war_room_service.py` RED before implementation, then GREEN.
- `uv run --no-sync --extra dev ruff check app tests scripts`
- `uv run --no-sync --extra dev mypy app tests scripts`

## Acceptance Criteria

- Required tests are written first and RED is observed before production code changes for this ticket.
- GREEN is observed on the same targeted test set after implementation.
- New output is deterministic and redacted.
- Safety boundaries above are preserved.
- Ticket completion report lists code paths, tests, and verification evidence.
