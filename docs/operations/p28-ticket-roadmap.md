# OpsCat P28 Ticket Roadmap — Read-only Polling Runtime

P28 adds a local/mock polling runtime that schedules read-only connector polls, applies timeout/backoff/rate-limit behavior, converts responses through P26 adapters, and emits bounded telemetry batches.

Boundary: read-only polling only, fixture/local transport by default, no production mutation, no remediation execution, no auth feature.

## Tickets

### P28-001 Polling job schema

Acceptance:
- Represent source, fixture/transport, interval, timeout, jitter, and max batch size.
- Default job state is disabled until local config enables it.

### P28-002 Deterministic scheduler

Acceptance:
- Tick-based scheduler runs without wall-clock flakiness.
- Backoff and retry state survive between ticks.

### P28-003 Fixture transport

Acceptance:
- Transport reads source-shaped payloads from local fixtures only.
- Transport simulates timeout, rate-limit, malformed payload, and empty result cases.

### P28-004 Adapter pipeline integration

Acceptance:
- Polling outputs feed P26 adapters and produce TrendWindows.
- Malformed batches are isolated per source.

### P28-005 Runtime report CLI

Acceptance:
- CLI runs bounded ticks and writes JSON/Markdown reports.
- Reports show readiness, batch count, dropped batch reasons, and risk windows.

### P28-006 Safety regression tests

Acceptance:
- No write/mutation capability can be scheduled.
- No unbounded retries or loops.
- No secret values in reports.

### P28-007 Verification integration

Acceptance:
- Add polling smoke to verification.
- Keep full verification live-call-free.

### P28-008 Release evidence

Acceptance:
- Document that P28 is live-like local polling, not production unattended operation.
