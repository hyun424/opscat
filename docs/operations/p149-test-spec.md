# P149 Canary Outcome Control Test Specification

Schema/status: `p149.report.v1`, `p149.freeze_manifest.v1`,
`p149.final_review.v1`, `p149.release_evidence.v1`, and
`p149_canary_outcome_control_qualified`. Artifacts and command are the exact P149
entries in the program plan.

1. Canary cohort and target identity are hash-bound and disjoint from controls.
2. Maximum affected target count is one and production/staging targets are rejected.
3. SLO uses a 60-second window, at least 5 observations, improvement >=10%,
   harm >=5%, and relative uncertainty <=2%.
4. Improvement commits the lab canary; no-change, harm, timeout, missing evidence, or contradiction rolls back.
5. Rollback is idempotent, verified, and cannot silently report success.
   Every case carries an exact P148 committed receipt binding for target,
   idempotency key, and closed rollback handler. Arbitrary hashes, missing
   commitments, duplicate case IDs, and extra case IDs are rejected.
6. Kill switch blocks new canaries and forces safe closure of an active canary.
7. Replay cannot apply or roll back an effect twice.
8. Report binds P148, outcomes, counters, limitations, and self-hash; release
   evidence requires the exact PROFILE case set to pass 8/8.
9. Canonical qualification rereads the exact canonical case path and content,
   sets `canonical_input_verified=true`, and requires that value for release.
   Explicit isolated-test reports set it false and cannot be promoted.
