---
id: P15-006
title: Offline Testability
status: DONE
phase: P15
depends_on: []
---

# P15-006 — Offline Testability

## Outcome

Implement the P15 slice for Offline Testability.

## Acceptance Criteria

- [x] Unit tests use fake NVIDIA/OpenAI-compatible clients.
- [x] Normal CI/full verify performs no external calls.
- [x] Network opt-in is documented separately.

## Boundary

No auth/session work, no default external model/API calls, no network calls during normal verification, no committed API keys, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no action execution, and no unattended production-operation claim.
