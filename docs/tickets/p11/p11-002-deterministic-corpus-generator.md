---
id: P11-002
title: Deterministic Corpus Generator
status: TODO
phase: P11
depends_on: [P11-001]
---

# P11-002 — Deterministic Corpus Generator

## Outcome

Implement the P11 slice for Deterministic Corpus Generator.

## Acceptance Criteria

- [ ] generates at least 50 cases
- [ ] case IDs are stable and unique
- [ ] each case has incident, evidence, rubric, tags, local_mock_only

## Boundary

No auth/session work, no external dataset download, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.
