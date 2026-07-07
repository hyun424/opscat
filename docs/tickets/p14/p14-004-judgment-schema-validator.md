---
id: P14-004
title: Judgment Schema Validator
status: TODO
phase: P14
depends_on: []
---

# P14-004 — Judgment Schema Validator

## Outcome

Implement the P14 slice for Judgment Schema Validator.

## Acceptance Criteria

- [ ] Validator rejects malformed JSON-like responses.
- [ ] Validator rejects invalid routes and malformed hypotheses/actions.
- [ ] Validator reports validation errors for CLI/reporting.

## Boundary

No auth/session work, no default external model/API calls, no network calls during normal verification, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, no action execution, and no unattended production-operation claim.
