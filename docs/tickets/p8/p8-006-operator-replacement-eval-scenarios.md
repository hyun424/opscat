---
id: P8-006
title: Scenario Pack v2: Operator-Replacement Evals
status: TODO
phase: P8
depends_on: [P8-001, P8-003, P8-004, P8-005]
boundary: no-auth-local-mock
---

# P8-006 — Scenario Pack v2: Operator-Replacement Evals

## Outcome

Expand replay scenarios so operator-replacement claims are measured by fixtures.

## Non-Negotiable Boundaries

- Do not add OIDC, SSO, login, password, browser session, or CSRF auth work.
- Do not add real production mutation, Kubernetes/cloud/database execution, unrestricted shell execution, customer credentials, or hosted SaaS claims.
- Automatic actions must remain local/mock, allowlisted, policy-gated, simulated, audited, and reversible.

## Allowed / Likely Paths

- `evals/replay/**`
- `app/services/replay_service.py`
- `scripts/run_replay_evals.py`
- `tests/test_p8_replay_evals.py`

## Implementation Plan

1. Add RED replay/eval tests requiring P8 scenario summary and fixture schema fields.
2. Add at least 40 P8 scenario fixtures across multi-service outage, alert storm, deploy/provider ambiguity, stale/poisoned memory, runbook mismatch, rollback-worsens-blast-radius, simulation pass/post-check fail, safe staging auto-action, unsafe prod block, missing logs/strong metrics, false-positive, and quiet-hours Night Autopilot blocked.
3. Every scenario records expected route, blocked/allowed action, missing evidence, expected human question, and reliability score band.
4. Wire replay output into full verify path if needed without breaking P7 compatibility.

## TDD / Verification Plan

- `uv run --no-sync --extra dev pytest -q tests/test_p8_replay_evals.py`
- `uv run --no-sync --extra dev python scripts/run_replay_evals.py --output-json /tmp/opscat-p8-replay.json --output-md /tmp/opscat-p8-replay.md`

## Acceptance Criteria

- Required tests are written first and RED is observed before production code changes for this ticket.
- GREEN is observed on the same targeted test set after implementation.
- New output is deterministic and redacted.
- Safety boundaries above are preserved.
- Ticket completion report lists code paths, tests, and verification evidence.
