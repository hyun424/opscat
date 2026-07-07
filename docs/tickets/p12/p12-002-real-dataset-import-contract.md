---
id: P12-002
title: Real Dataset Import Contract
status: TODO
phase: P12
depends_on: [P12-001]
---

# P12-002 — Real Dataset Import Contract

## Outcome

Implement the P12 slice for Real Dataset Import Contract.

## Acceptance Criteria

- [ ] import API accepts only local files/directories
- [ ] unknown or missing paths fail with actionable errors
- [ ] import results include accepted/skipped/unsupported/redacted counts

## Boundary

No auth/session work, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.
