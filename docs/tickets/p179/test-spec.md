# P179 Test Spec

## Claims Under Test

1. OpsCat self-monitoring detects runtime failure.
2. Restart/resume preserves ledger continuity and prevents duplicates.
3. Monitor uncertainty demotes the system before action readiness.
4. Kill switch and deadman remain authoritative.

## Matrix

- Unit tests for health state, generation IDs, demotion reasons, and dedupe.
- Integration tests for process restart, provider outage, queue lag, model
  timeout, storage corruption, and resource ceiling breach.
- Wall-clock soak with injected failures and signed start/end receipts.
- Negative tests for stale heartbeat, forged checkpoint, duplicate request ID,
  deadman expiry, and kill-switch race.

## Pass Gates

- `restart_resume_seconds <= 60`.
- `duplicate_decision_count == 0`.
- `monitor_blind_interval_count == 0`.
- `failed_demote_count == 0`.
- `kill_switch_drill_pass_rate == 1.0`.
- `production_mutation_count == 0`.
