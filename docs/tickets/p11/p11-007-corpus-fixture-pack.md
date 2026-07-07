---
id: P11-007
title: Corpus Fixture Pack
status: DONE
phase: P11
depends_on: [P11-002, P11-004]
---

# P11-007 — Corpus Fixture Pack

## Outcome

Implement the P11 slice for Corpus Fixture Pack.

## Acceptance Criteria

- [x] fixture has at least 50 cases
- [x] includes safety/no-data/false-positive/conflicting/cascading cases
- [x] fixture is local/mock and redacted

## Boundary

No auth/session work, no external dataset download, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.
