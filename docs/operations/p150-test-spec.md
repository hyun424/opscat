# P150 Unattended Chaos Soak Test Specification

Schema/status: `p150.report.v1`, `p150.freeze_manifest.v1`,
`p150.final_review.v1`, `p150.release_evidence.v1`, and
`p150_unattended_chaos_soak_qualified`. Artifacts and command are the exact P150
entries in the program plan.

1. Accelerated clock represents seven days with deterministic ordered ticks and no real sleep.
2. Exercise healthy, incident, evidence-gap, injection, provider failure, model failure, crash, restart, lease conflict, storage pressure, harmful canary, rollback, and kill-switch cases.
3. Heartbeats, cursor advancement, deduplication, restart recovery, and deadman events reconcile exactly.
4. Every action effect reaches verified commit or verified rollback; unresolved effects fail qualification.
5. Fast-run limits are queue depth 256, artifact bytes 16,777,216, two retries
   and 64 work units per tick. The qualifying wall-clock run is exactly 7,200
   one-second cycles with elapsed >=7,200 seconds, heartbeat age <=3 seconds,
   deadman threshold 5 seconds, RSS growth <=67,108,864 bytes, artifacts
   <=33,554,432 bytes, and queue depth <=256.
6. Repeated runs have identical semantic hashes despite different artifact roots.
7. No credential, external endpoint, external provider, staging mutation, or production mutation occurs.
8. Report binds P149 and the schedule/profile/source hashes.
9. Fast fixtures cover the 12 closed fault classes. Wall-clock evidence is a
   runner result plus an append-only, self-hashed and chain-linked JSONL cycle
   ledger and an atomic checkpoint. Their raw file hashes, real monotonic-ns
   start/end, resource maxima, start/resume receipts, runner identity, and
   runner mode are mutually bound. Canonical qualification accepts only
   `real_monotonic_sleep`; injected test clocks are valid only for isolated
   test evidence. Partial, in-memory, tampered, accelerated, underreported,
   or force-ended runs cannot set `wall_clock_qualified=true`.
10. Final P150 report and release validation requires exact success metrics:
    13 of 13 cases passed, zero failed, zero unresolved effects, exactly 7,200
    wall-clock cycles, reported wall-clock seconds exactly 7,200, exact fast
    resource limits, and ledger-derived resource maxima with no rounding or
    underreporting.
11. Release evidence carries a closed `wall_clock_evidence` object with raw
    result, ledger, and checkpoint file hashes; wall-clock receipt and start
    receipt hashes; runner identity; runner mode; ledger entry count and final
    entry hash; checkpoint hash; and resource-maxima hash so final audit does
    not depend on hidden profile preimage state. The report metric
    `wall_clock_evidence_hash` equals the canonical hash of this exact object,
    preventing runner mode or raw-artifact commitments from being rewritten
    after report freeze and independent review.
