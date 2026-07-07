---
id: P14-001
title: LLM Judgment Provider Interface
status: TODO
phase: P14
depends_on: []
---

# P14-001 — LLM Judgment Provider Interface

## Outcome

Implement the P14 slice for LLM Judgment Provider Interface.

## Acceptance Criteria

- [ ] Provider protocol supports deterministic mock provider and future opt-in provider adapters.
- [ ] Default provider is local/mock and performs no network calls.
- [ ] Provider output is plain JSON-compatible data.

## Boundary

No auth/session work, no default external model/API calls, no network calls during normal verification, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, no action execution, and no unattended production-operation claim.
