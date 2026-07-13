# P136 Test Specification

## Contract and finite authority

- Accept only exact-key, self-hashed P136 configs, checkpoints, reservations,
  entries, intents, promotions, and termination receipts.
- Reject unknown/missing fields, booleans in integer fields, invalid timestamps,
  unsafe paths, overlapping roots/state paths, and credential/network/command-
  shaped configuration.
- Require complete canonical P134 contract, review, receipt ledger, and receipt
  bytes as runtime inputs; hash references alone are insufficient.
- Revalidate the full receipt-ledger chain, membership, distinctness, cumulative
  counters, current validity windows, clock rollback, proposal level/method/
  capability/source/attempt, and whole-index byte/line estimates.
- Atomically write and directory-fsync a deterministic
  `p136.index_read_intent.v1` before any index open/read. It binds checkpoint,
  cycle, receipt, complete authority inputs, source, and maximum read budgets.
- Permit receipt retry only from the exact durable uncommitted reservation.
  Reject attempted reuse without it and consume the receipt permanently after
  checkpoint.
- Stop on finite pool exhaustion; require each real segment read to use a fresh
  P134 receipt validated through its independent P135 bundle.

## Secure index scanner

- Use descriptor-relative `O_NOFOLLOW` traversal and reject symlink parents,
  final symlinks, hardlinks, directories, devices, FIFOs, and non-owner-safe
  state files.
- Detect file replacement during read using pre/post descriptor and directory
  entry identity.
- Read no more than whole-index/file/cycle limits and rehash the complete
  committed prefix on every cycle.
- Defer an incomplete final line with exact pending byte hash, length, old file
  identity, line-start cursor, and observed size. Advance observed size but not
  committed cursor/prefix.
- Require a same-identity completion to preserve pending bytes exactly.
- Reject duplicate JSON keys, non-finite numbers, invalid UTF-8, excess depth,
  nodes, strings, line bytes, total bytes, and complete-line count.

## Cursor and rotation

- Same identity plus append resumes at the exact committed cursor.
- Same identity plus shrink or consumed-prefix change fails closed.
- Reject identity change while an old-identity partial is pending.
- A new identity may start with bounded exact canonical replay entries. Resolve
  them from P136 state without invoking P135.
- Require the first unseen new-identity entry to continue global sequence and
  bind both previous and rotation hashes to the prior committed entry.
- Empty/partial rotated files remain pending; replay-only rotation is accepted
  only after all complete replay bytes match canonical state.
- Rotation gap, rollback, fork, lineage mismatch, or conflicting ID reuse fails
  closed without advancing the prior checkpoint.

## Duplicate-first P135 bridge

- Resolve duplicate/restart/rotation replay from the durable P136 promotion and
  canonical identity map before P135; assert zero segment open/read activity.
- Exercise all five real P135 adapter profiles through one-artifact manifests.
- Use one independent P135 manifest and one independent P135 receipt ledger per
  first-seen entry; never claim multiple per-entry results share one ledger.
- Revalidate P134 segment receipt membership, expected bytes/records/content,
  adapter identity, normalized P120 records, P135 execution receipt, and ledger.
- Bind the P136 promotion key to config, entry, P134 contract/ledger/receipt,
  P135 manifest/artifact/adapter/content/bundle/execution-receipt/ledger hashes.
- Reject a rehashed changed source, provider/format, artifact binding, P120 raw
  provenance, execution receipt, bundle, or independent ledger.
- Persist parser/redaction/provenance failures only as denominator-visible failed
  promotion records. Pre-read failures report zero segment reads.
- Assert promotion exactly once; do not claim read or attachment exactly once.

## Durability and recovery

- Write/fsync/directory-fsync index-read reservation before read, promotion intent
  before promotion, and promotion before checkpoint.
- Crash after reservation before read and after read before P135 resumes the exact
  cycle with the same reservation and no new receipt.
- Crash after promotion intent replays the exact intent to one promotion.
- Crash after promotion advances checkpoint without P135 or another promotion.
- Equivalent reservation/intent/promotion paths are idempotent; conflicting
  bytes fail closed.
- Corrupt, stale, semantically inconsistent, or rehashed-forged checkpoint,
  reservation, intent, promotion, chain, or P135 per-entry state fails closed.
- Pre-replace failure preserves prior state; post-replace directory-fsync
  uncertainty stops explicitly.
- Journal/promotion budget exhaustion blocks rather than deleting evidence.

## Lease, loop, failure, and signals

- Acquire one nonblocking exclusive lease before any state, index, or segment
  read; in-process and real competitors perform zero such activity.
- One-cycle mode reserves and consumes one index receipt.
- Bounded loop mode uses monotonic cadence and stops on maximum cycles, receipt
  exhaustion, failure threshold, SIGINT, or SIGTERM.
- Termination receipts bind stop reason, safe-boundary final checkpoint, consumed
  and reserved receipts, and exact counters.
- Signal handlers set only a stop flag; SIGINT/SIGTERM receipt tests execute at a
  safe boundary and evaluator signal activity is separate.
- Runtime time is compared with the durable checkpoint before any observation
  activity. Rollback beyond `max_clock_rollback_ms` fails with
  `clock_rollback_exceeded`; tolerated rollback never moves checkpoint time
  backwards.

## Exact measurement and leak safety

- Validate the exact `forbidden_authority`, `runtime_activity`,
  `evaluator_activity`, and `resource_usage` key sets defined by the roadmap;
  reject booleans, negatives, unknown keys, and stamped values.
- Prove runtime guard attempts against provider/network/DNS/socket, environment,
  credential, subprocess, shell, signal, delivery, remediation, and mutation are
  blocked; promotable forbidden counters remain exact integer zero.
- Derive duplicate segment-read and promotion counts from repeated entry-hash
  probe events. Case summaries and aggregate release totals must equal those
  measurements; fixed zero fields are not accepted.
- Require positive local index and segment activity where expected, exact zero
  segment reads on duplicate/pre-read failures, and measured reservation/
  promotion/checkpoint/fsync/recovery counts.
- Measure wall with a monotonic clock, self and child CPU with
  `resource.getrusage`, and normalize the P136 interval's macOS/Linux peak-RSS
  growth to bytes rather than charging an embedding process's prior peak.
- Promoted artifacts contain no absolute path, credentials, prompt injection
  text, raw secret values, or unredacted provider payload.

## Canonical release matrix

The canonical runner executes the exact 50 cases enumerated in
`p136-incremental-observer-roadmap.md`, compares every outcome/rejection with its
exact expected semantics, and independently rebuilds all totals. Required totals:

- 50 expected, 50 passed, 0 failed;
- five provider first-batch promotions;
- zero duplicate promotions and zero duplicate segment reads across duplicate,
  restart, rotation, and crash recovery;
- all config/path, authority, partial/rotation, P135 tamper, crash, durability,
  lease, exhaustion, failure-threshold, signal, guard, and resource claims
  represented in the denominator;
- all exact-schema and release gates true;
- resources within 30 s wall, 15 s self-plus-child CPU, and 128 MiB peak RSS;
- exact release status
  `p136_incremental_local_observation_qualified`.
- a complete current-source independent-review artifact is mandatory input to
  release-evidence validation; structural validation without it is non-release.

## Verification sequence

1. Targeted failing P136 tests, then implementation until green.
2. Targeted Ruff and Mypy.
3. Independent code review and resolution.
4. Canonical 50-case run to a temporary directory.
5. `bash scripts/verify.sh --profile p136-release`.
6. Full repository verification in a loopback-capable environment.
7. P122 security/docs evidence refresh if source bindings require it.
8. Secret/path scan, `git diff --check`, Lore commit, private push, and
   local/remote/private-state confirmation.

The standalone runner defaults release output to `evals/p136/output`, separate
from `evals/p136/independent-review.json`, and cleanup explicitly preserves
profile/review inputs even when a caller chooses an overlapping directory.
