# P105-016 - Release-Qualified Evidence Contract

## Goal

Define the machine-checkable contract for P105 release-qualified evidence while
preserving the existing smoke-only path and P106 default lock.

## Tests First

- Add RED contract tests for `smoke_only`, `smoke_only_missing_mode`, and
  `release_qualified` mode semantics.
- Add RED tests proving locked smoke evidence cannot unlock P106 or receive
  release floor pass credit.
- Add RED tests requiring the existing held-out, real-derived,
  source-diversity, and service-day floors for every supported family.
- Add RED tests for fail-closed missing numerators, denominators, mode fields,
  split IDs, family IDs, source counts, incident-group counts, and coverage
  values.
- Add RED tests requiring a pre-scoring source-availability manifest with
  per-family rows, positives, incidents, source tuples, review-redaction
  status, and local hashes.

## Implementation Notes

- Keep this ticket contract-first. Do not change P106 thresholds.
- The qualified artifact is a future generated artifact, not the current
  committed tiny fixture.
- The contract must name separate locked smoke and qualified artifacts.

## Acceptance

- `smoke_only` and `smoke_only_missing_mode` always emit
  `release_qualified=false` and `p106_unlocked=false`.
- `release_qualified=true` requires every existing P105 floor and every P106
  gate row to be present and passing.
- Missing or unevaluable evidence blocks release qualification and P106 unlock.
- Availability floors are compared before scoring, and expansion beyond actual
  availability is smoke/diagnostic only.
- Release docs state that implementation is not complete until tests are GREEN
  and qualified evidence exists.

## Acceptance Commands

Future implementation must make this command pass after first observing RED:

```bash
uv run --no-sync --extra dev pytest -q \
  tests/test_p105_release_qualified_evidence_contract.py
```

Documentation-only planning validation for this ticket:

```bash
git diff --check
bash scripts/verify.sh --profile docs
```

## Stop Condition

Stop if smoke evidence can unlock P106, any existing floor is weakened, missing
denominators pass, source availability is not checked before scoring, or
release docs imply that qualified evidence already exists.
