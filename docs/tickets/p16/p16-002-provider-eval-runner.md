---
id: P16-002
title: Provider Eval Runner
status: TODO
phase: P16
depends_on: []
---

# P16-002 — Provider Eval Runner

## Outcome

Implement the P16 slice for Provider Eval Runner.

## Acceptance Criteria

- [ ] Runner evaluates a sequence of JudgmentCase objects with mock or explicit provider.
- [ ] Runner records provider, model, latency_ms, pass/fail, and per-case reasons.
- [ ] Runner does not execute actions.

## Boundary

No auth/session work, no default external model/API calls during normal verification, no committed or printed API keys, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no action execution, and no unattended production-operation claim.
