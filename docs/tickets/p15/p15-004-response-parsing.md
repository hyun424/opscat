---
id: P15-004
title: Response Parsing
status: TODO
phase: P15
depends_on: []
---

# P15-004 — Response Parsing

## Outcome

Implement the P15 slice for Response Parsing.

## Acceptance Criteria

- [ ] Provider extracts JSON from non-stream or stream-like responses.
- [ ] Invalid JSON fails closed via P14 validation.
- [ ] Reasoning content is not required or persisted.

## Boundary

No auth/session work, no default external model/API calls, no network calls during normal verification, no committed API keys, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no action execution, and no unattended production-operation claim.
