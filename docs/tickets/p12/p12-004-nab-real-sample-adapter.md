---
id: P12-004
title: NAB Real Sample Adapter
status: TODO
phase: P12
depends_on: [P12-002, P12-006]
---

# P12-004 — NAB Real Sample Adapter

## Outcome

Implement the P12 slice for NAB Real Sample Adapter.

## Acceptance Criteria

- [ ] supports timestamp/value windows and optional anomaly labels
- [ ] produces spike, no-data, stale, and healthy/false-positive cases
- [ ] stores baseline/current/ratio signal metadata deterministically

## Boundary

No auth/session work, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.
