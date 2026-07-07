---
id: P16-003
title: Mock Baseline Smoke
status: DONE
phase: P16
depends_on: []
---

# P16-003 — Mock Baseline Smoke

## Outcome

Implement the P16 slice for Mock Baseline Smoke.

## Acceptance Criteria

- [x] Mock provider evaluation is fully offline and deterministic.
- [x] Mock smoke runs in verify eval/full.
- [x] Normal verification performs no NVIDIA calls.

## Boundary

No auth/session work, no default external model/API calls during normal verification, no committed or printed API keys, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no action execution, and no unattended production-operation claim.
