---
id: P13-006
title: Runbook Context Selector
status: DONE
phase: P13
depends_on: [P13-005]
---

# P13-006 — Runbook Context Selector

## Outcome

Implement the P13 slice for Runbook Context Selector.

## Acceptance Criteria

- [x] selects likely runbooks by incident text and hypotheses
- [x] includes allowed local/mock actions and forbidden actions
- [x] keeps production mutation and unrestricted shell disallowed

## Boundary

No auth/session work, no model calls, no external API calls, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.
