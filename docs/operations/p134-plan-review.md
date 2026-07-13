# P134 Independent Plan Review

## First review: rejected

The independent critic found one P0 contradiction and four material gaps:
duplicate evaluations were required both to leave the ledger unchanged and to
increment a duplicate ledger counter; schemas and reason codes were not exact;
budget transitions were ambiguous; runtime and evaluator authority were mixed;
and independent review provenance plus `p134-release` wiring were unspecified.

## First correction

- Duplicate evaluation now returns the original receipt and byte-identical
  ledger with only an out-of-band `duplicate=true` result.
- Exact contract, review, proposal, receipt, ledger, counter, hash, timestamp,
  reason-order, budget, and denial-transition rules are fixed.
- Runtime authority, evaluator activity, and evaluator authority have separate
  closed counter schemas.
- A separately authored, source-bound independent-review artifact is required;
  unauthenticated reviewer identity remains an explicit limitation.
- Dedicated `scripts/verify.sh` wiring and mechanical no-execution claim gates
  are required.

## Second review: rejected

The critic found that unique host and method budget-denial cases were impossible
because OA1 allowed only one host and one method. It also found the first receipt
link had no defined genesis value.

## Second correction

- OA1 now supports bounded synthetic `local-artifact.*` policy aliases and
  `LOCAL_STAT`, `LOCAL_READ_FILE`, and `LOCAL_LIST_DIR` declarations. These make
  budgets testable without adding a path, hostname, or filesystem operation.
- The first receipt uses an exact contract/window-derived genesis hash.
- Outside-window, rollback, and sequence errors are structural and leave the
  ledger unchanged.

## Third review: rejected

The roadmap had the structural-error rule, but the test spec still described
clock rollback and sequence gaps as denied receipts.

## Final correction and decision

The test spec now requires structural rejection, no receipt, and a byte-identical
ledger for outside-window, rollback, and sequence mismatch. The final independent
review returned **APPROVE** with no remaining blocker or P135/P136 scope leak.
Implementation may begin under the approved test-first contract.

## Pre-implementation semantic-binding amendment

A final local readiness check found that a receipt containing only
`proposal_hash` could not independently prove byte, record, host, method, and
capability counter deltas. The receipt contract was therefore strengthened to
embed the complete canonical proposal, which contains only bounded labels and
hashes. Ledger validation must recompute every transition from that embedded
proposal. This amendment requires an additional independent review before code
implementation.

The additional independent critic returned **APPROVE**. It confirmed the
embedded proposal is bounded, hash-verifiable, non-secret, no-I/O, and does not
expand P134 into P135/P136. It requested one direct tamper regression, which was
added before implementation.
