---
id: P16-006
title: Failure Analysis
status: DONE
phase: P16
depends_on: []
---

# P16-006 — Failure Analysis

## Outcome

Implement the P16 slice for Failure Analysis.

## Acceptance Criteria

- [x] Failed cases include reason strings.
- [x] Unknown citations, invalid schema, unsafe allowed actions, and route mismatch are explicit.
- [x] Markdown highlights safety regressions separately.

## Boundary

No auth/session work, no default external model/API calls during normal verification, no committed or printed API keys, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no action execution, and no unattended production-operation claim.
