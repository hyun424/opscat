---
id: P12-007
title: Dataset Fixture Pack
status: DONE
phase: P12
depends_on: [P12-003, P12-004, P12-005]
---

# P12-007 — Dataset Fixture Pack

## Outcome

Implement the P12 slice for Dataset Fixture Pack.

## Acceptance Criteria

- [x] includes one LogHub-shaped sample, one NAB-shaped sample, and one AIOps-shaped sample
- [x] fixtures are small, redacted, synthetic-or-license-safe excerpts
- [x] fixture manifest explains provenance and boundary

## Boundary

No auth/session work, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.
