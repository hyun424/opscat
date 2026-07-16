# P160 Plan Review

Decision: approved with bounded claim.

- Poll the P159 observation surface without sleeping inside core logic.
- Inject clock values for deterministic tests.
- Distinguish service incident, telemetry stale, connector unavailable, and
  healthy states.
- Emit heartbeat/deadman evidence on every cycle.
- Deduplicate unchanged incident fingerprints without hiding state changes.
