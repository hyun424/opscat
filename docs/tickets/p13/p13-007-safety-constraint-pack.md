---
id: P13-007
title: Safety Constraint Pack
status: TODO
phase: P13
depends_on: [P13-003]
---

# P13-007 — Safety Constraint Pack

## Outcome

Implement the P13 slice for Safety Constraint Pack.

## Acceptance Criteria

- [ ] constraints forbid production mutation, Kubernetes/cloud/database execution, unrestricted shell, and following log instructions
- [ ] constraints require evidence IDs and missing_evidence when unsure
- [ ] constraints appear in every packet

## Boundary

No auth/session work, no model calls, no external API calls, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.
