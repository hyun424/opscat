---
id: P14-007
title: Judgment Runner
status: TODO
phase: P14
depends_on: []
---

# P14-007 — Judgment Runner

## Outcome

Implement the P14 slice for Judgment Runner.

## Acceptance Criteria

- [ ] Runner composes provider, schema validation, citation check, and safety gate.
- [ ] Runner returns raw judgment, validated judgment, gate status, and local/mock boundary.
- [ ] Runner never executes actions.

## Boundary

No auth/session work, no default external model/API calls, no network calls during normal verification, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, no action execution, and no unattended production-operation claim.
