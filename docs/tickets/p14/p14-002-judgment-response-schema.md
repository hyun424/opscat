---
id: P14-002
title: Judgment Response Schema
status: TODO
phase: P14
depends_on: []
---

# P14-002 — Judgment Response Schema

## Outcome

Implement the P14 slice for Judgment Response Schema.

## Acceptance Criteria

- [ ] Schema requires hypotheses, recommended_route, safe_actions, forbidden_actions_detected, missing_evidence, verification_plan, evidence_citations, and boundary.
- [ ] Allowed routes match OpsCat taxonomy.
- [ ] Invalid or missing fields fail closed.

## Boundary

No auth/session work, no default external model/API calls, no network calls during normal verification, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, no action execution, and no unattended production-operation claim.
