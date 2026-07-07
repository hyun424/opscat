---
id: P11-005
title: Benchmark Smoke Selector
status: TODO
phase: P11
depends_on: [P11-002, P11-003]
---

# P11-005 — Benchmark Smoke Selector

## Outcome

Implement the P11 slice for Benchmark Smoke Selector.

## Acceptance Criteria

- [ ] selects diverse deterministic smoke subset
- [ ] covers key routes and tags
- [ ] can include P10 seed plus P11 corpus cases

## Boundary

No auth/session work, no external dataset download, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.
