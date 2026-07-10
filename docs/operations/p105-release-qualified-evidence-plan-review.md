# P105 Release-Qualified Evidence Plan Review

Status: third repair recorded after second REVISE. This document records the
independent critic blockers reported for the initial G006 documentation-only
planning commit, the first repair items, the second narrow command repair, and
the third honest reviewed-local P44 pipeline repair. It does not claim
independent approval or re-approval.

## Review Scope

Initial reviewed commit:

```text
75d1995403a017dafb5356069399604e2cb1657b
```

Reviewed artifacts:

- `docs/operations/p105-release-qualified-evidence-plan.md`
- `docs/operations/p105-release-qualified-evidence-test-spec.md`
- `docs/operations/p105-ticket-roadmap.md`
- `docs/tickets/p105/README.md`
- `docs/tickets/p105/p105-016-release-qualified-evidence-contract.md`
- `docs/tickets/p105/p105-017-deterministic-local-materializer.md`
- `docs/tickets/p105/p105-018-locked-smoke-artifact.md`
- `docs/tickets/p105/p105-019-qualified-artifact-generation.md`
- `docs/tickets/p105/p105-020-parity-partition-coverage-isolation.md`
- `docs/tickets/p105/p105-021-reproducibility-and-tamper-tests.md`
- `docs/tickets/p105/p105-022-independent-review-full-verification.md`

## Initial Verdict

Independent critic verdict: REVISE.

The initial plan was documentation-only and correctly avoided implementation
claims, but it left release-qualification loopholes that could let insufficient
or non-reconstructable evidence appear stronger than it is.

## Blockers and Repairs

1. P44 disabled versus reviewed-local P44 was under-specified.
   Repair: the plan and test spec now split a P44-disabled negative command
   that must remain locked from a reviewed-local P44 positive command, and they
   require a source-availability preflight manifest with per-family rows,
   positives, incidents, source tuples, review-redaction status, and local
   hashes.

2. Private scorer-label and answer-key integrity was incomplete.
   Repair: the plan and tests now require a private answer-key ledger, separate
   label hashes bound to canonical tuple, offset, incident group, and
   derivation ID, metrics source-of-truth semantics, and label tamper tests both
   with unchanged public hashes and with recomputed public hashes.

3. P24 parity could still fall back to non-identical inputs.
   Repair: the plan and parity ticket now require exact per-row reconstructable
   P24 input parity, ban fallback to unrelated seed windows or fixture
   defaults, and require a parity manifest with `source_window_id`, input hash,
   `RiskSignal` hash, `RiskForecast` hash, and denominator alignment status.

4. Source availability and anti-clone gates were missing before scoring.
   Repair: the materializer, contract, artifact, and tamper docs now require
   unique materialized record hashes per independent record, at most one release
   row per canonical tuple, offset, window, incident key, availability-floor
   comparison before scoring, and smoke/diagnostic-only status for expansion
   beyond actual availability.

5. Planning files needed EOF whitespace cleanup.
   Repair: the planning files were checked for whitespace defects with
   `git diff --check`; the resulting commit must also pass `git show --check`.

## Current Review Status

Second independent critic verdict: REVISE.

The second review found stale command examples where `--p44-mode disabled`
still wrote to release-qualified output paths with `--mode release_qualified`
and no `--expect-locked`. That stale pattern contradicted the first repair:
disabled P44 examples must be explicitly locked and non-qualified, while
positive release-qualified and reproducibility examples must use reviewed-local
P44.

Second repair:

- Removed the stale disabled-P44 release-qualified materializer example from
  `docs/operations/p105-release-qualified-evidence-plan.md`.
- Removed the same stale example from
  `docs/operations/p105-release-qualified-evidence-test-spec.md`.
- Updated `docs/tickets/p105/p105-021-reproducibility-and-tamper-tests.md` so
  the release-qualified rerun uses `--p44-reviewed-local-manifest` and
  `--p44-mode reviewed-local`.
- Preserved the P44-disabled negative examples only where they use a locked
  output path plus `--expect-locked`.

The repair documentation is ready for another independent review. Until that
review returns an explicit APPROVE verdict, G006 remains in second
REVISE-repaired status and must not be described as independently approved or
re-approved.

## Third Repair: Honest Reviewed-Local P44 Pipeline

The third repair closes an additional release-qualification loophole: G006
could still be interpreted as allowing ordinal, partition-position, max-value,
or otherwise synthetic public-source signals to satisfy P44-backed floors.

Repair:

- Updated `docs/operations/p105-release-qualified-evidence-plan.md` to require
  label-blind deterministic sampling from raw public source bytes before any
  NAB official label join, LogHub scorer-ledger incident creation, partition
  assignment, floor accounting, P24/P105 score use, or private label access.
- Updated the plan to require NAB `combined_windows.json` labels to join only
  after sampling and only in the private scorer-label ledger, with no max-value
  fallback, peak-value relabeling, threshold-created positives, ordinal
  positives, or synthetic anomaly labels.
- Updated the plan to allow LogHub incidents only through a deterministic
  private scorer ledger with reviewed parser version, burst predicate, line
  offsets, source-window boundaries, incident groups, and source hashes.
- Updated the plan to require public features and P24 `TrendWindow` inputs to
  come from the same sampled source record/window before private labels are
  joined.
- Updated `docs/operations/p105-release-qualified-evidence-test-spec.md` with
  future RED expectations and assertions for label-blind sampling, official
  NAB post-sampling label joins, deterministic LogHub error-burst ledgers,
  source-to-family proxy limitations, privacy/redaction/license/citation
  manifests, committed-derived-artifact-only boundaries, and exact
  provenance/hash/tamper checks.
- Updated `docs/operations/p105-ticket-roadmap.md` to name the implementation,
  command, artifact, and test boundaries and to keep the existing per-family
  floors unchanged. If honest sources cannot meet those floors, the roadmap now
  requires G006 to stay locked and add reviewed sources rather than fabricate
  labels or lower gates.

The repair documentation is ready for another independent review. Until that
review returns an explicit APPROVE verdict, G006 remains in
third-repair-after-second-REVISE status and must not be described as
independently approved or re-approved.

## Verification Required for Repair Commit

Run:

```bash
git diff --check
rg -- "--p44-mode disabled|--p44-mode reviewed-local|--expect-locked|--output-dir /tmp/opscat-p105-release-qualified" docs
bash scripts/verify.sh --profile docs
git show --check --stat HEAD
```

Stop if any command fails or if the commit includes code, tests, fixtures, or
implementation claims.

Additional third-repair checks:

```bash
rg -- "label-blind|combined_windows|max-value|LogHub|error-burst|privacy/redaction/license/citation|provenance-hash|ordinal|partition-position" docs/operations/p105-release-qualified-evidence-plan.md docs/operations/p105-release-qualified-evidence-test-spec.md docs/operations/p105-ticket-roadmap.md
git diff --name-only HEAD
```
