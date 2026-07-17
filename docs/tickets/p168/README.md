# P168 Tickets

Dependency: canonical P167 release. Owner surface: soak runner in the shared
service, P168 fixture/tests, runner/verifier, and `evals/p168`.

1. **P168-001 — Scheduler.** Run 120 deterministic virtual cycles with the
   configured healthy/precursor/incident mix and no sleep or human approval.
2. **P168-002 — Recovery drills.** Restart after cycle 60, trip kill switch twice,
   expire deadman twice, and inject two harmful action mismatches. Positive-test
   resume/rollback; negative-test any escaped or repeated action.
3. **P168-003 — Resource/effect gates.** Verify hash-chain completeness, at most
   1 MiB total artifacts, 4096 bytes/cycle ledger growth, four files, 15 seconds
   local runtime, and zero unresolved/healthy/duplicate/deadman/unsafe effects.
4. **P168-004 — Final evidence.** Emit explicit
   `wall_clock_24h_completed=false`, maximum mode, forbidden claims, and
   production blockers. Done after final review, sequential P164-P168 evidence
   validation, >=80% service coverage, and full repository verification.
