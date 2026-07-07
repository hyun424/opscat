---
id: P12-003
title: LogHub Real Sample Adapter
status: TODO
phase: P12
depends_on: [P12-002, P12-006]
---

# P12-003 — LogHub Real Sample Adapter

## Outcome

Implement the P12 slice for LogHub Real Sample Adapter.

## Acceptance Criteria

- [ ] supports timestamp, level/label, component, message, anomaly/session labels
- [ ] produces anomaly, false-positive, and unknown-log-anomaly cases
- [ ] preserves source metadata without leaking secrets

## Boundary

No auth/session work, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.
