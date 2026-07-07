---
id: P8-007
title: War Room Report Export
status: TODO
phase: P8
depends_on: [P8-001, P8-003, P8-004, P8-005]
boundary: no-auth-local-mock
---

# P8-007 — War Room Report Export

## Outcome

Export a redacted Markdown war-room report suitable for demo/review.

## Non-Negotiable Boundaries

- Do not add OIDC, SSO, login, password, browser session, or CSRF auth work.
- Do not add real production mutation, Kubernetes/cloud/database execution, unrestricted shell execution, customer credentials, or hosted SaaS claims.
- Automatic actions must remain local/mock, allowlisted, policy-gated, simulated, audited, and reversible.

## Allowed / Likely Paths

- `app/services/report_service.py`
- `app/services/war_room_service.py`
- `docs/operations/**`
- `tests/test_war_room_report_export.py`

## Implementation Plan

1. Add RED tests for required report sections and redaction.
2. Implement export using war room read model.
3. Ensure generated report artifacts are not tracked in git.
4. Include incident summary, timeline, evidence, hypotheses, reliability score, policy gates, human questions, and final decision.

## TDD / Verification Plan

- `uv run --no-sync --extra dev pytest -q tests/test_war_room_report_export.py`
- `bash scripts/verify.sh --profile docs`

## Acceptance Criteria

- Required tests are written first and RED is observed before production code changes for this ticket.
- GREEN is observed on the same targeted test set after implementation.
- New output is deterministic and redacted.
- Safety boundaries above are preserved.
- Ticket completion report lists code paths, tests, and verification evidence.
