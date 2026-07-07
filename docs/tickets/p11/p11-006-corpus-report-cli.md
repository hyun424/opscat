---
id: P11-006
title: Corpus Report CLI
status: TODO
phase: P11
depends_on: [P11-003, P11-004]
---

# P11-006 — Corpus Report CLI

## Outcome

Implement the P11 slice for Corpus Report CLI.

## Acceptance Criteria

- [ ] writes JSON and Markdown reports
- [ ] exits non-zero on quality gate failure
- [ ] does not download or call external services

## Boundary

No auth/session work, no external dataset download, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.
