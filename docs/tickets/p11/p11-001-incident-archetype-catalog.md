---
id: P11-001
title: Incident Archetype Catalog
status: DONE
phase: P11
depends_on: []
---

# P11-001 — Incident Archetype Catalog

## Outcome

Implement the P11 slice for Incident Archetype Catalog.

## Acceptance Criteria

- [x] catalog covers at least 17 SRE failure modes
- [x] each archetype has hypotheses, tags, evidence hints, expected route, forbidden actions
- [x] catalog is deterministic and local/mock only

## Boundary

No auth/session work, no external dataset download, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.
