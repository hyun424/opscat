---
id: P10-007
title: Judgment Benchmark Runner
status: DONE
phase: P10
depends_on: [P10-005, P10-006]
boundary: no-auth-local-mock
---

# P10-007 — Judgment Benchmark Runner

## Outcome

Implement the P10 slice for Judgment Benchmark Runner.

## Non-Negotiable Boundaries

- Do not add OIDC, SSO, login, password, browser session, or CSRF auth work.
- Do not add real production mutation, Kubernetes/cloud/database execution, unrestricted shell execution, customer credentials, or hosted SaaS claims.
- Do not download external datasets during normal verification.
- Automatic actions must remain local/mock, allowlisted, policy-gated, simulated, audited, and reversible.

## Allowed / Likely Paths

- `app/services/judgment_benchmark.py`
- `scripts/run_judgment_benchmark.py`
- `tests/test_judgment_benchmark.py`

## Acceptance Focus

run and score cases.

## TDD / Verification Plan

1. Read `docs/operations/p10-ticket-roadmap.md` and this ticket.
2. Write RED tests for this ticket's acceptance criteria.
3. Verify RED failure is caused by missing intended behavior.
4. Implement the smallest deterministic local/mock slice.
5. Run targeted tests, ruff, mypy, and relevant verification profiles.
6. Mark this ticket DONE only after GREEN evidence.

## Completion Criteria

- Required tests pass.
- Output is deterministic and redacted where text may contain secrets.
- No external provider/network/shell execution is introduced.
- Ticket completion report lists code paths, tests, and verification evidence.
