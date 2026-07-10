# P105-029 - Independent Review, Full Verification, and P106 Gate

## Goal

Close G006 source expansion only after independent code review, independent
architecture review, full verification, and explicit P106 gate evaluation.

## Scope

- source-expanded implementation diff
- source-expanded artifacts and hashes
- independent code review
- independent architecture review
- targeted tests, fast verification, docs verification, coverage gate
- P106 lock/unlock decision

## Tests First

- Review and release docs tests must require independent code and architecture
  review evidence after actual source runs and benchmark.
- Tests must fail if docs claim P106 unlock without the exact gate payload.

## Implementation Notes

- Implementation output cannot self-approve.
- Code review checks behavior, tests, artifacts, privacy/license handling, and
  release documentation.
- Architecture review checks family authority, source eligibility, local-only
  queue/deploy isolation, no production authority, and P106 sequencing.
- P106 can start only after full verification and a passing exact gate payload.

## Acceptance

- Independent code review returns APPROVE or all findings are repaired and
  re-reviewed.
- Independent architecture review returns CLEAR or all blockers are repaired
  and re-reviewed.
- Verification evidence includes targeted source-expansion tests, existing
  P105-RQ tests, release benchmark, docs profile, fast profile, coverage gate,
  artifact hashes, and no known errors.
- `release_qualified=true` and `p106_unlocked=true` appear only if every
  unchanged floor, P106 gate row, provenance, partition, coverage, parity,
  privacy/license, reproducibility, tamper, review, and authority gate passes.
- Otherwise the release artifact records `release_qualified=false`,
  `p106_unlocked=false`, and a concrete stop reason.

## Acceptance Commands

```bash
uv run --no-sync --extra dev pytest -q \
  tests/test_p105_source_registry_eligibility.py \
  tests/test_p105_source_expansion_contract.py \
  tests/test_p105_dejavu_a1_materializer.py \
  tests/test_p105_log_parser_materializers.py \
  tests/test_p105_queue_harness_materializer.py \
  tests/test_p105_deploy_harness_materializer.py \
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

Stop if either independent review rejects, verification fails, artifact hashes
are missing, release docs overclaim, P106 gate evidence is missing or failed,
or any production authority, credential, synthetic-padding, label-leakage, or
unsupported-family counting defect remains.
