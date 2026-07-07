---
id: P13-002
title: Evidence Selector
status: TODO
phase: P13
depends_on: [P13-001]
---

# P13-002 — Evidence Selector

## Outcome

Implement the P13 slice for Evidence Selector.

## Acceptance Criteria

- [ ] ranking prioritizes errors, anomalies, deploy markers, metrics, no-data/stale signals, and safety-risk content
- [ ] selector enforces max evidence limit
- [ ] selector keeps evidence IDs stable

## Boundary

No auth/session work, no model calls, no external API calls, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.
