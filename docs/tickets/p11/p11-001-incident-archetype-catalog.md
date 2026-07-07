---
id: P11-001
title: Incident Archetype Catalog
status: TODO
phase: P11
depends_on: []
---

# P11-001 — Incident Archetype Catalog

## Outcome

Implement the P11 slice for Incident Archetype Catalog.

## Acceptance Criteria

- [ ] catalog covers at least 17 SRE failure modes
- [ ] each archetype has hypotheses, tags, evidence hints, expected route, forbidden actions
- [ ] catalog is deterministic and local/mock only

## Boundary

No auth/session work, no external dataset download, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.
