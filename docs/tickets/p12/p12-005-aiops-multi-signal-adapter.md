---
id: P12-005
title: AIOps Multi-signal Adapter
status: TODO
phase: P12
depends_on: [P12-002, P12-006]
---

# P12-005 — AIOps Multi-signal Adapter

## Outcome

Implement the P12 slice for AIOps Multi-signal Adapter.

## Acceptance Criteria

- [ ] supports JSON/JSONL incident records with logs, metrics, events, incident_type, root_cause labels
- [ ] emits required evidence for every signal family present
- [ ] maps labels into expected hypotheses, route, and verification criteria

## Boundary

No auth/session work, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.
