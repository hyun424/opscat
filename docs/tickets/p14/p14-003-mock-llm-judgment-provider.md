---
id: P14-003
title: Mock LLM Judgment Provider
status: TODO
phase: P14
depends_on: []
---

# P14-003 — Mock LLM Judgment Provider

## Outcome

Implement the P14 slice for Mock LLM Judgment Provider.

## Acceptance Criteria

- [ ] Mock provider consumes P13 context packets and returns deterministic judgment.
- [ ] Prompt-injection/unsafe evidence is surfaced as forbidden action evidence, not instructions.
- [ ] Mock output cites existing evidence IDs.

## Boundary

No auth/session work, no default external model/API calls, no network calls during normal verification, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, no action execution, and no unattended production-operation claim.
