# P170 Test Spec

- Start, status, resume, stop, and verify a read-only staging shadow soak.
- Pre-register poll interval, expected source denominator, outage taxonomy, and
  resource ceilings before `start`.
- Prove 24 real elapsed hours from signed UTC start/end receipts plus
  per-process monotonic segments with boot/session IDs.
- Keep real provider failures in the frozen denominator unless signed external
  outage or injection evidence reclassifies them.
- Require polling success at least 99.9% and watchdog records for heartbeat gaps
  over two configured polling intervals.
- Restart/resume within 60 seconds without duplicate evidence, skipped ledger
  generations, actions, or mutations.
- Verify artifact growth, memory, CPU, file count, request rate, retry budgets,
  and all write/action/mutation counters remain within the frozen limits.
