---
id: P11-003
title: Corpus Audit Metrics
status: TODO
phase: P11
depends_on: [P11-002]
---

# P11-003 — Corpus Audit Metrics

## Outcome

Implement the P11 slice for Corpus Audit Metrics.

## Acceptance Criteria

- [ ] reports total, route counts, tag counts, source counts, duplicates, missing evidence, missing hypotheses
- [ ] fails missing safety/no-data/false-positive/route-diversity coverage
- [ ] output is deterministic JSON

## Boundary

No auth/session work, no external dataset download, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.
