# P105-022 - Independent Review and Full Verification

## Goal

Close the G006 release-qualified evidence sequence only after independent
review, full verification, and explicit stop-condition evidence.

## Tests First

- Add RED docs/release tests requiring the review ledger to record independent
  review status, reviewer scope, rejection findings, repairs, and final
  verdict.
- Add RED tests requiring release docs to include locked smoke status,
  qualified artifact hash, exact floors, exact P106 gate rows, P24 parity,
  provenance, partition, coverage, reproducibility, tamper, and authority
  evidence.
- Add RED tests requiring release docs to include source-availability preflight,
  private label-ledger, P44-disabled negative command, reviewed-local P44
  positive command, P24 parity manifest, and anti-clone evidence.
- Add RED tests proving P106 unlock claims are absent unless the exact gate
  payload passes.
- Add RED tests requiring verification evidence for docs, targeted P105 tests,
  fast verification, and benchmark commands.

## Implementation Notes

- Independent review owns the review verdict. Implementation output cannot
  self-approve.
- A rejection keeps release qualification blocked until repaired and
  re-reviewed.
- Do not create production authority, auth scope, live connector dependencies,
  or remediation execution.

## Acceptance

- The review ledger links the exact qualified artifact hash and verification
  outputs reviewed.
- The review ledger names whether review returned APPROVE, REVISE, or REJECT;
  repair documentation must not claim re-approval without a later verdict.
- Release docs distinguish current implementation evidence from planned work.
- Full verification is recorded with commands and results.
- P106 remains locked unless the final gate payload passes with hard-zero
  authority counters.

## Acceptance Commands

Future implementation must make these commands pass after first observing RED:

```bash
uv run --no-sync --extra dev pytest -q \
  tests/test_p105_release_qualified_evidence_contract.py \
  tests/test_p105_release_qualified_materializer.py \
  tests/test_p105_release_qualified_artifacts.py \
  tests/test_p105_release_qualified_reproducibility.py \
  tests/test_p105_release_evidence.py \
  tests/test_failure_forecast_engine.py
```

```bash
bash scripts/verify.sh --profile docs
bash scripts/verify.sh --profile fast
```

## Stop Condition

Stop if independent review rejects the evidence, full verification fails, docs
claim implementation that does not exist, repair notes claim re-approval without
a later verdict, any authority counter is nonzero, or the final P106 gate
payload is missing, failed, or unevaluable.
