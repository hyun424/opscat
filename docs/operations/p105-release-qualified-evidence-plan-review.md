# P105 Release-Qualified Evidence Plan Review

Status: second REVISE recorded. This document records the independent critic
blockers reported for the initial G006 documentation-only planning commit, the
first repair items, and the second narrow command repair. It does not claim
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
