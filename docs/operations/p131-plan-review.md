# P131 Plan Review

## Verdict

Approved after one safety correction: P131 is a standalone process, not a
FastAPI lifespan task, and its promoted scope is local JSONL only.

## Reviewed decisions

- **Independent process:** avoids duplicate monitor loops under multiple API
  workers and allows an external supervisor/watchdog to detect process death.
- **Monotonic absolute cadence:** missed deadlines are counted and skipped;
  the runtime never performs catch-up bursts.
- **Durable cursor generation:** source identity, cursor, recent observation
  hashes, canary, heartbeat, report watermark, and authority are committed in
  one self-hashed atomic state file.
- **Separate live/ready:** current heartbeat is not enough when source data is
  stale, failure limits are exceeded, or the canary fails.
- **Narrow canary:** the synthetic probe covers internal serialization, signal
  detection, and the no-action contract; source freshness separately covers the
  external JSONL delivery path.
- **Bounded ingestion:** per-cycle byte, record, and line-size limits prevent an
  unbounded drain or oversized-line allocation.
- **Exact-zero authority:** P121 counters are exact-key and exact-integer zero;
  raw observations are never stored in state or health reports.

## Rejected alternative

Direct Prometheus polling was removed from P131. P121 defines
`live_connector_call_count` as an authority counter, so a real network GET and
an exact-zero claim cannot both be true. A future phase must first introduce and
review a truthful read-only observation contract.

## Remaining risk

Fake-clock and deterministic release evidence prove contracts, not 24-hour
availability. Process-supervisor recovery and long soak evidence remain future
qualification work and are not represented as complete.
