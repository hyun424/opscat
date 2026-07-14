# P137-010 - Final verification

## Scope

Run the final P137 verification sequence and close the release only when all
contract, handoff, authority, runner, final-review, and repository gates pass.

## Acceptance

- Contract/schema, P136 ingest, correlation, hypothesis, request,
  classification, ledger, durability, recovery, lease, signal, CAS, hash
  namespace, budget, and resource tests pass.
- Direct P136 handoff tests invoke
  `validate_incremental_observer_config(p136_config)`,
  `validate_observer_runtime_authority(p136_config, authority, now=now)` with
  only the contract/review/ledger/index byte fields it validates plus
  `segment_receipts` mappings, and
  `validate_promotion_record(promotion, expected_entry=expected_entry,
  runtime=runtime)` over supplied bytes with zero provider reads. P137
  independently validates `segment_receipt_bytes` before constructing that
  authority; P136 is not claimed to validate segment receipt bytes.
- Final verification includes stale-alias grep and a runtime-vs-profile key
  check proving every delta-profile key is canonical and every materialized row
  has a full post-override map.
- Static authority scan and evaluator-injected fake-callable guard probes prove
  forbidden authority is blocked with exact-zero runtime counters and statically
  banned runtime imports.
- Ruff, Mypy, docs checks, preliminary canonical 60-case runner freeze, final
  source-bound review, and `bash scripts/verify.sh --profile p137-release`
  pass in that order.
- Final frozen-source implementation review has zero unresolved P0/P1/P2
  findings and is present before release validation.
- Full repository verification passes in a loopback-capable local environment.
- Secret/path scan and `git diff --check` pass before the Lore commit and
  private push.
