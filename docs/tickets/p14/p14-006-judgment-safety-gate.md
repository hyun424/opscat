---
id: P14-006
title: Judgment Safety Gate
status: TODO
phase: P14
depends_on: []
---

# P14-006 — Judgment Safety Gate

## Outcome

Implement the P14 slice for Judgment Safety Gate.

## Acceptance Criteria

- [ ] Forbidden actions force blocked or human_required routes.
- [ ] Non-mock or production-like actions are removed from safe_actions.
- [ ] Safety gate emits deterministic gate reasons.

## Boundary

No auth/session work, no default external model/API calls, no network calls during normal verification, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, no action execution, and no unattended production-operation claim.
