---
id: P13-009
title: Context Builder CLI
status: TODO
phase: P13
depends_on: [P13-001, P13-002, P13-003, P13-004, P13-005, P13-006, P13-007, P13-008]
---

# P13-009 — Context Builder CLI

## Outcome

Implement the P13 slice for Context Builder CLI.

## Acceptance Criteria

- [ ] CLI accepts --cases, --case-id, --output-json, --output-md
- [ ] CLI writes deterministic JSON and reviewer markdown
- [ ] CLI does not call models or external services

## Boundary

No auth/session work, no model calls, no external API calls, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.
