---
id: P16-004
title: NVIDIA Live Eval Opt-in
status: DONE
phase: P16
depends_on: []
---

# P16-004 — NVIDIA Live Eval Opt-in

## Outcome

Implement the P16 slice for NVIDIA Live Eval Opt-in.

## Acceptance Criteria

- [x] CLI supports --provider nvidia with safe .env parsing.
- [x] NVIDIA live eval can limit max cases.
- [x] API key is never printed or persisted.

## Boundary

No auth/session work, no default external model/API calls during normal verification, no committed or printed API keys, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no action execution, and no unattended production-operation claim.
