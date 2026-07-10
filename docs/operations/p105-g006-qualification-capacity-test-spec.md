# P105 G006 Qualification-Capacity Test Spec

Status: planning only. These tests are future RED-to-GREEN requirements for the
qualification-capacity amendment. No implementation may begin before independent
plan approval.

## RED contract batch

Add focused tests for database, queue, and deploy fleet profiles that initially
fail because `p105.actual-fleet-soak.256x1h.v1` does not exist.

Required assertions:

- legacy exact harness profiles remain byte-compatible and cannot receive fleet
  credit accidentally;
- the fleet profile accepts exactly 256 unique services, fixed 128/128 partitions,
  3,600 requested seconds, 720 samples, offsets 0..3,595, and a five-second
  observation cadence;
- profile configuration is hashed and frozen before private schedule loading;
- public config and telemetry contain no labels, incident answer keys, scorer
  thresholds, floor deficits, or release outcomes;
- queue evidence comes from `actual_rabbitmq_docker`; deploy evidence comes from
  `actual_threading_http_server`;
- every counting interval is reconstructed from adjacent observed monotonic
  samples with a raw delta in 4.0..7.5 seconds, conservatively bucketed by the
  reviewed formula, receipt-bound, and unioned per source/family/split/service;
- missing samples reduce measured coverage; requested duration never substitutes
  for observed duration;
- fleet materialization rejects the legacy `created_at + tick_seconds` coverage
  path and consumes only receipt-bound fleet coverage segments;
- each private incident binds to exact already-sampled public source-window IDs;
- duplicate source-window/row identities cannot multiply positives, duplicate
  group IDs cannot multiply groups, and duplicate service intervals cannot
  multiply coverage; distinct precursor windows sharing one incident remain
  legitimate distinct positive rows under the unchanged scorer;
- rerun artifacts prove reproducibility but add zero release-floor credit;
- all three families emit exactly frozen g00..g07 groups per split, disjoint
  four-service runtime resources, exact starts/kinds/private failure timestamps,
  family-compatible 45..50m, 35..40m, or 25..30m precursor lead times, and 96
  controls;
- database enforces 64 shard files/pools, 192 connections, 40,000 SQL cycles,
  64 workers, 1 GiB memory, 512 MiB SQLite storage, and 256 MiB output maxima;
- queue enforces 35,872 messages, 512 queues, eight concurrent management
  operations, 80,000 management calls, 1 GiB memory, 512 MiB disk, and 256 MiB
  output maxima;
- deploy enforces 184,320 requests, 64 threads/sockets, two-second timeout, 1 KiB
  response, 512 MiB memory, and 256 MiB output maxima;
- registry and materializer accept fleet roots only through `database_fleet`,
  `queue_fleet`, and `deploy_fleet` closed adapters and reject
  cross-profile/schema substitution;
- telemetry loss, runtime-health failure, partial cleanup, or envelope mismatch
  produces a locked non-counting receipt;
- no auth, credential lookup, external host, production mutation, action plan,
  or action execution path is introduced.

## Integration and release tests

The integration test must run a short non-counting diagnostic profile to exercise
actual runtime plumbing, then validate committed deterministic fixtures for the
full profile. Only separately executed full one-hour actual runs may receive a
runtime qualification receipt.

The release sequence must prove:

1. deficient baseline sources produce `release_qualified=false` with exact
   deficits and no fabricated credit;
2. full database, queue, and deploy run 1 receipts bind canonical roots, raw attestations,
   registry, eligibility, review ledger, and frozen profile hashes;
3. run 2 canonical files are byte-identical to run 1 while raw volatile hashes
   remain independently enveloped;
4. central materialization consumes only receipt-authorized source entries;
5. the benchmark recomputes row, positive, group, diversity, coverage,
   calibration, useful-lead-time, false-alert, parity, and authority gates;
6. P106 unlock occurs only when every unchanged gate passes.

## Verification profiles

P105-034 must run, at minimum:

```bash
uv run --no-sync --extra dev pytest -q tests/test_p105_*.py tests/test_failure_forecast_engine.py
uv run --no-sync --extra dev ruff check app scripts tests
uv run --no-sync --extra dev mypy app scripts
bash scripts/verify.sh --profile fast
bash scripts/verify.sh --profile docs
bash scripts/verify.sh --profile coverage
```

Actual-runtime and Docker tests may require the repository's documented elevated
local-test permission. They must remain isolated and non-production.
