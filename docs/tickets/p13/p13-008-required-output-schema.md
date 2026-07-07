---
id: P13-008
title: Required Output Schema
status: DONE
phase: P13
depends_on: [P13-001, P13-007]
---

# P13-008 — Required Output Schema

## Outcome

Implement the P13 slice for Required Output Schema.

## Acceptance Criteria

- [x] schema requires hypotheses, recommended_route, safe_actions, forbidden_actions_detected, missing_evidence, verification_plan, evidence_citations
- [x] allowed routes match OpsCat taxonomy
- [x] schema is included in packets and docs

## Boundary

No auth/session work, no model calls, no external API calls, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.
