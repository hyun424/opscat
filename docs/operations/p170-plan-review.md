# P170 Plan Review

Decision: approved for real 24-hour read-only wall-clock shadow soak only.

- Build on the durable ledger, heartbeat, deadman, and restart/resume behavior
  from the P164-P168 program.
- Derive `wall_clock_24h_completed=true` only from signed UTC start/end receipts
  plus per-process monotonic segments carrying boot/session IDs.
- Freeze poll interval, expected source denominator, outage taxonomy, and
  resource ceilings before `start`.
- Keep real provider failures in the frozen denominator unless separately signed
  external outage or injection evidence justifies classification.
- Require watchdog events for heartbeat gaps, restart/resume within 60 seconds,
  bounded artifacts/resources, and exact-zero write/action/mutation counters.
