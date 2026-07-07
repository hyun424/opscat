---
id: P16-005
title: JSON and Markdown Reports
status: DONE
phase: P16
depends_on: []
---

# P16-005 — JSON and Markdown Reports

## Outcome

Implement the P16 slice for JSON and Markdown Reports.

## Acceptance Criteria

- [x] CLI writes provider eval JSON and Markdown.
- [x] Reports include aggregate score, pass rate, safety regressions, and failures.
- [x] Reports include artifact paths and boundary text.

## Boundary

No auth/session work, no default external model/API calls during normal verification, no committed or printed API keys, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no action execution, and no unattended production-operation claim.
