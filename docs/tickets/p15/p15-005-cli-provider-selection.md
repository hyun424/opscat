---
id: P15-005
title: CLI Provider Selection
status: DONE
phase: P15
depends_on: []
---

# P15-005 — CLI Provider Selection

## Outcome

Implement the P15 slice for CLI Provider Selection.

## Acceptance Criteria

- [x] scripts/run_llm_judgment.py accepts --provider nvidia.
- [x] CLI accepts --model override and env default.
- [x] Mock remains the default provider.

## Boundary

No auth/session work, no default external model/API calls, no network calls during normal verification, no committed API keys, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no action execution, and no unattended production-operation claim.
