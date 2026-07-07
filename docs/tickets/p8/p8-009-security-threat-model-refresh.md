---
id: P8-009
title: P8 Security and Threat Model Refresh
status: TODO
phase: P8
depends_on: [P8-001, P8-003, P8-004, P8-005, P8-002]
boundary: no-auth-local-mock
---

# P8-009 — P8 Security and Threat Model Refresh

## Outcome

Document and test risks introduced by war room, scoring, memory, and runbook suggestions.

## Non-Negotiable Boundaries

- Do not add OIDC, SSO, login, password, browser session, or CSRF auth work.
- Do not add real production mutation, Kubernetes/cloud/database execution, unrestricted shell execution, customer credentials, or hosted SaaS claims.
- Automatic actions must remain local/mock, allowlisted, policy-gated, simulated, audited, and reversible.

## Allowed / Likely Paths

- `docs/security-review-p8.md`
- `docs/threat-model.md`
- `docs/release-evidence.md`
- `tests/test_p8_security_docs.py`

## Implementation Plan

1. Add RED documentation contract tests for required threat phrases and boundary language.
2. Document stale/poisoned memory, over-trusting reliability score, prompt/log injection, secret exposure, unsafe runbook suggestions, and UI overclaiming production autonomy.
3. Map mitigations to tests/evals.
4. Preserve explicit auth deferral.

## TDD / Verification Plan

- `uv run --no-sync --extra dev pytest -q tests/test_p8_security_docs.py`
- `bash scripts/verify.sh --profile docs`

## Acceptance Criteria

- Required tests are written first and RED is observed before production code changes for this ticket.
- GREEN is observed on the same targeted test set after implementation.
- New output is deterministic and redacted.
- Safety boundaries above are preserved.
- Ticket completion report lists code paths, tests, and verification evidence.
