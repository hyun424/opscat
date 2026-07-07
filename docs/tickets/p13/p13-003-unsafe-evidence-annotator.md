---
id: P13-003
title: Unsafe Evidence Annotator
status: DONE
phase: P13
depends_on: [P13-002]
---

# P13-003 — Unsafe Evidence Annotator

## Outcome

Implement the P13 slice for Unsafe Evidence Annotator.

## Acceptance Criteria

- [x] detects unsafe prompt/log-injection phrases
- [x] unsafe content stays evidence but never becomes instructions
- [x] packet includes risk_flags and instruction_trust

## Boundary

No auth/session work, no model calls, no external API calls, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.
