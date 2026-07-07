---
id: P13-005
title: Candidate Hypothesis Context
status: TODO
phase: P13
depends_on: [P13-001, P13-002]
---

# P13-005 — Candidate Hypothesis Context

## Outcome

Implement the P13 slice for Candidate Hypothesis Context.

## Acceptance Criteria

- [ ] hypotheses come from rubric, incident, or deterministic root-cause service
- [ ] hypotheses include confidence, supporting evidence IDs, and missing evidence
- [ ] packet instructs LLM to review candidates instead of inventing causes

## Boundary

No auth/session work, no model calls, no external API calls, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.
