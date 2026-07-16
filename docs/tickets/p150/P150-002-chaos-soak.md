# P150-002 — Accelerated chaos soak

Status: DONE

- Implement deterministic seven-day fast schedule, the exact two-hour
  wall-clock qualifying runner, and all required fault transitions.
- Prove continuity, bounded resources, recovery, rollback closure, and semantic replay.
- Depends on: P150-001.
- Write scope: `app/services/p150_unattended_soak.py` plus frozen helpers only.
- Acceptance: 604800 simulated seconds, all 12 frozen fault classes, semantic
  replay match, unresolved effects zero, frozen resource ceilings, then 7,200
  successful one-second wall-clock cycles and `wall_clock_qualified=true`.
- Stop: accelerated-path wall-clock dependency, qualifying-path injected time or
  skipped sleep/cycle, unbounded queue/artifact growth, continuity loss, or
  replay divergence.
