---
id: P12-008
title: Dataset Conversion CLI
status: TODO
phase: P12
depends_on: [P12-003, P12-004, P12-005, P12-007]
---

# P12-008 — Dataset Conversion CLI

## Outcome

Implement the P12 slice for Dataset Conversion CLI.

## Acceptance Criteria

- [ ] CLI supports --family loghub, --family nab, and --family aiops
- [ ] CLI writes judgment cases and import quality report
- [ ] CLI refuses download URLs and remote paths

## Boundary

No auth/session work, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.
