---
id: P14-008
title: LLM Judgment CLI
status: TODO
phase: P14
depends_on: []
---

# P14-008 — LLM Judgment CLI

## Outcome

Implement the P14 slice for LLM Judgment CLI.

## Acceptance Criteria

- [ ] CLI accepts a P13 context packet or judgment cases/case-id input.
- [ ] CLI writes deterministic JSON and Markdown reports.
- [ ] CLI defaults to mock provider and performs no external calls.

## Boundary

No auth/session work, no default external model/API calls, no network calls during normal verification, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, no action execution, and no unattended production-operation claim.
