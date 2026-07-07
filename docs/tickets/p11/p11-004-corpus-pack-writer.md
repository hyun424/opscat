---
id: P11-004
title: Corpus Pack Writer
status: DONE
phase: P11
depends_on: [P11-002, P11-003]
---

# P11-004 — Corpus Pack Writer

## Outcome

Implement the P11 slice for Corpus Pack Writer.

## Acceptance Criteria

- [x] writes sorted corpus JSON
- [x] redacts secret-like values
- [x] stores pack under evals/judgment/corpus

## Boundary

No auth/session work, no external dataset download, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.
