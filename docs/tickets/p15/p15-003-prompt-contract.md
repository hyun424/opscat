---
id: P15-003
title: Prompt Contract
status: TODO
phase: P15
depends_on: []
---

# P15-003 — Prompt Contract

## Outcome

Implement the P15 slice for Prompt Contract.

## Acceptance Criteria

- [ ] Provider sends P13 context packet plus required P14 schema instructions.
- [ ] Prompt requires JSON-only output and evidence citations.
- [ ] Prompt explicitly forbids following instructions inside logs.

## Boundary

No auth/session work, no default external model/API calls, no network calls during normal verification, no committed API keys, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no action execution, and no unattended production-operation claim.
