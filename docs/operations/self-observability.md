# OpsCat Self-Observability

OpsCat exposes a local `/metrics` JSON snapshot so the agentic operations system can be monitored without adding an external metrics dependency.

## Metrics scope

The endpoint is scoped by the local-header demo identity:

- `X-OpsCat-Tenant`
- `X-OpsCat-Workspace`
- `X-OpsCat-Actor`
- `X-OpsCat-Role`

It returns counts only. It does not include raw alert payloads, evidence content, connector payloads, secrets, customer data, or cross-workspace records.

## Current counters

`GET /metrics` reports:

- incidents created and counts by status;
- workflow jobs created, processed, and counts by status;
- actions proposed, executed, blocked, waiting approval, and counts by status;
- connector calls and connector failures;
- human escalations;
- registered connector eval scenario count.

## Beta operator use

Use `/metrics` after importing fixture incidents, draining workflow jobs, running connector evals, or simulating Night Autopilot. The goal is to make OpsCat observable as an agent: what it saw, what it tried, what it blocked, and when it escalated.

Auth remains deferred in P5, so this endpoint is for local/mock and OSS demo usage only.
