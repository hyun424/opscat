---
id: P15-001
title: NVIDIA Provider Interface
status: DONE
phase: P15
depends_on: []
---

# P15-001 — NVIDIA Provider Interface

## Outcome

Implement the P15 slice for NVIDIA Provider Interface.

## Acceptance Criteria

- [x] NVIDIA provider uses OpenAI-compatible API with base_url https://integrate.api.nvidia.com/v1.
- [x] Default model is nvidia/nemotron-3-ultra-550b-a55b.
- [x] Provider is opt-in and never used by normal verify profiles.

## Boundary

No auth/session work, no default external model/API calls, no network calls during normal verification, no committed API keys, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no action execution, and no unattended production-operation claim.
