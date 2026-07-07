---
id: P16-001
title: Provider Eval Case Scoring
status: TODO
phase: P16
depends_on: []
---

# P16-001 — Provider Eval Case Scoring

## Outcome

Implement the P16 slice for Provider Eval Case Scoring.

## Acceptance Criteria

- [ ] Each judgment case produces schema, citation, route, hypothesis, evidence, forbidden-action, safety, and overall scores.
- [ ] Scoring reuses P13 context and P14 judgment result.
- [ ] Scores are deterministic and redacted.

## Boundary

No auth/session work, no default external model/API calls during normal verification, no committed or printed API keys, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no action execution, and no unattended production-operation claim.
