# P170 Tickets

Dependency: canonical P169 attachment-runtime readiness evidence. Final live
promotion additionally requires P169 observed attachment evidence. Owner surface: P170
supervisor, checkpoint ledger, watchdog status, resource accounting, command
entry points, and P170 documentation only until implementation begins.

1. **P170-001 — Frozen run manifest.** Pre-register poll interval, expected
   source denominator, outage taxonomy, resource ceilings, retry budgets, and
   source/provider set before `start`.
2. **P170-002 — Wall-clock proof.** Derive 24-hour completion from signed UTC
   start/end receipts plus per-process monotonic segments carrying boot/session
   IDs. Reject virtual time, configuration-derived completion, and a single
   monotonic clock spanning restart.
3. **P170-003 — Polling and outage accounting.** Keep real provider failures in
   the frozen denominator unless separately signed external outage or injection
   evidence justifies classification. Require at least 99.9% polling success.
4. **P170-004 — Watchdog and resume.** Emit watchdog events for heartbeat gaps
   over two configured polling intervals and resume within 60 seconds without
   duplicate evidence, skipped ledger generations, actions, or mutations.
5. **P170-005 — Resource and authority evidence.** Done when artifact growth,
   memory, CPU, file count, request rate, retry budgets, and exact-zero
   write/action/mutation counters satisfy the frozen limits.
