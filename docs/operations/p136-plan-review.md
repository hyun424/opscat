# P136 Independent Plan Review

## Scope

This artifact records the independent implementation-readiness review of the
P136 roadmap, test specification, and tickets. Review is read-only and separate
from plan authorship.

## Round 1

Verdict: `REQUEST CHANGES`.

### P0 resolution

- Added durable `p136.index_read_intent.v1` reservation before any index
  open/read.
- Bound checkpoint state/hash, full authority input hashes, receipt, cycle ID,
  source/method/capability, and whole-index byte/line budgets.
- Restricted receipt retry to the exact durable uncommitted reservation.

### P1 resolutions

- Replaced hash-only authority inputs with full P134 contract, review, receipt
  ledger, and ordered receipt bytes plus chain/membership/distinctness/current-
  window/proposal/cumulative-budget validation.
- Moved duplicate/restart/rotation replay resolution before P135 and required
  zero segment reads unless a fresh receipt governs a new attachment.
- Chose one independent P135 manifest and receipt-ledger namespace per first-seen
  entry; P136 promotion records store the complete independent tuple.
- Defined pending partial byte hash/length/file identity/line-start/observed-size
  semantics and fail-closed rotation after old-identity partial state.

### P2 resolutions

- Expanded the fixed denominator from 36 to 50 substantive cases covering exact
  config/path topology, clock rollback, SIGINT/SIGTERM, receipt exhaustion,
  failure threshold, runtime guard probes, rotated empty/partial states, P135
  semantic tamper, and both index-reservation crash windows.
- Added exact forbidden-authority, runtime-activity, evaluator-activity, and
  resource schemas including monotonic wall time, self/child `getrusage`, and
  cross-platform RSS normalization.

### P3 resolutions

- Copied every high-risk reservation, authority, duplicate-first, ledger-
  namespace, partial/rotation, stop/signal, and exact-evidence acceptance
  criterion into its owning executor ticket.

## Round 2

Verdict: `APPROVE`.

The same independent reviewer re-read the current plan bytes and reported zero
unresolved P0/P1/P2 findings. One nonblocking P3 wording ambiguity was found:
whether the 15-second CPU limit covered evaluator self CPU or self-plus-child
CPU. The roadmap and test specification now explicitly apply the limit to the
sum of `cpu_time_ms` and `child_cpu_time_ms`.

Final implementation-readiness verdict: `APPROVE`.
