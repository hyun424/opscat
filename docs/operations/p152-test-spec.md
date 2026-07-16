# P152 Integrated Operator-Agent Readiness Test Specification

Schema/status: `p152.report.v1`, `p152.freeze_manifest.v1`,
`p152.final_review.v1`, `p152.release_evidence.v1`, and
`p152_bounded_operator_agent_qualified`. Artifacts and command are the exact P152
entries in the program plan.

1. Validate exact final P146 and P147-P151 predecessor schemas, statuses, hashes, limitations, and source bindings.
2. Reject preliminary, stale, reordered, missing, non-release, or live-provider-only predecessor evidence.
3. Canonical qualification has exactly eight frozen rows, all in
   `approve_once`, and arbitrary eight-case `auto_safe_lab` fixtures cannot
   qualify. The rows are: valid local receipt, missing receipt, forged receipt,
   expired receipt, replayed receipt, action mismatch, target mismatch, and
   pre-state mismatch.
4. `approve_once` accepts only a local signed fixture receipt and rejects
   missing, self-issued, forged, expired, target/action/pre-state mismatched, or
   replayed receipts; it does not qualify remote auth and never executes.
5. Kill switch and deadman safety metrics are derived from the exact canonical
   rows, and release evidence must carry the exact canonical success metrics
   because release artifacts do not include rows.
6. Every action is idempotent, blast-radius bounded, postcondition checked, and rollback closed.
7. Final evidence requires independent review counts P0-P3 zero, where P0 is
   data loss/security/authority escape, P1 incorrect release/unresolved effect,
   P2 material correctness/operability, and P3 bounded maintainability/testing.
   P122, secret scan, focused coverage, and full verification are mandatory
   outer release-pipeline evidence; they are not claimed as fields bound inside
   the already-assembled P152 canonical release object.
8. Final report states `production_operator_replacement_ready=false`, zero staging/production mutation, exact limitations, and self-hash.
