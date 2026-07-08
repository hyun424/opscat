# OpsCat P34 Ticket Roadmap — Live Read-only Polling Runtime v2

P34 connects the P33 dry-run readiness gate to a read-only polling runtime. It polls only connectors marked ready by the dry-run harness, adapts local fixture payloads, emits telemetry snapshots/trend windows, and records skipped/blocked jobs. Boundary: no auth feature work, no live API calls by default, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.

## Tickets

- P34-001 — Polling v2 job manifest: define jobs linked to P33 connector IDs and local telemetry fixtures.
- P34-002 — Dry-run readiness gate: poll only P33-ready connectors; skip degraded and blocked connectors.
- P34-003 — Read-only enforcement: block any job declaring write/mutation behavior.
- P34-004 — Adapter integration: normalize polled fixtures through P26 telemetry adapters.
- P34-005 — Trend-window output: emit proactive trend windows for polled snapshots.
- P34-006 — Runtime scorecard: report polling success, readiness gate pass rate, blocked unsafe jobs, and live API call count.
- P34-007 — Verification integration: add P34 smoke to `scripts/verify.sh` and docs contract tests.
- P34-008 — Release evidence: record P34 artifacts, metrics, and safety boundary.

## Acceptance criteria

- Polls at least two ready read-only jobs.
- Skips degraded/blocked connectors from P33.
- Blocks at least one unsafe/write job.
- Emits at least four trend windows.
- Live API call count remains 0.
- JSON and Markdown reports are generated.
