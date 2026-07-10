# P105-023 - Source Registry, Eligibility Contract, and Plan Review

## Goal

Add the G006 source-expansion planning contract and require independent
plan-review approval before RED tests or implementation begin.

## Scope

- `docs/operations/p105-g006-source-expansion-amendment.md`
- `docs/operations/p105-g006-source-expansion-test-spec-amendment.md`
- future `p105-reviewed-source-registry.json`
- future `p105-source-eligibility-manifest.json`
- future `scripts/build_p105_source_registry.py`

## Tests First

- Add RED tests requiring a reviewed source registry before scoring.
- Add RED tests requiring a source eligibility manifest before scoring.
- Add RED tests proving unsupported-family rows are non-counting.
- Add RED tests requiring `command_argv`, `created_at`, provenance hashes,
  license, privacy, reviewer, and eligibility fields.
- Add RED docs tests requiring the plan-review artifact before source-expansion
  implementation can be marked complete.

## Implementation Notes

- The registry records candidate sources.
- The eligibility manifest is the only release-floor counting authority.
- P105-023 owns the source-registry producer schema and command; P105-028 owns
  invoking it during actual source runs and passing its root hashes downstream.
- Family authority must come from reviewed parser/adapter/harness metadata, not
  heuristics, filenames, record ordinals, labels, scores, or floor deficits.
- Do not change any P105 floor or P106 gate threshold.

## Acceptance

- Registry and eligibility manifests are mandatory before scoring.
- Missing registry, missing eligibility, or missing provenance fields locks the
  run.
- Unsupported-family rows support diagnostics only and do not count toward
  rows, positives, incident groups, source diversity, coverage, or floors.
- Independent plan review is recorded before the next macro step.

## Acceptance Commands

Future implementation:

```bash
uv run --no-sync --extra dev pytest -q \
  tests/test_p105_source_registry_eligibility.py \
  tests/test_p105_source_expansion_contract.py
```

Planning-only validation:

```bash
git diff --check
UV_CACHE_DIR=/private/tmp/opscat-uv-cache bash scripts/verify.sh --profile docs
```

## Stop Condition

Stop if a source can count without registry review, eligibility approval,
actual provenance binding, license/privacy metadata, or independent plan-review
evidence.
