---
id: P14-009
title: Prompt Injection Regression
status: TODO
phase: P14
depends_on: []
---

# P14-009 — Prompt Injection Regression

## Outcome

Implement the P14 slice for Prompt Injection Regression.

## Acceptance Criteria

- [ ] Prompt/log injection fixture remains blocked or human_required.
- [ ] Unsafe production restart/kubectl instructions are reported as forbidden actions.
- [ ] No unrestricted shell/Kubernetes/cloud/database action is emitted as safe.

## Boundary

No auth/session work, no default external model/API calls, no network calls during normal verification, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, no action execution, and no unattended production-operation claim.
