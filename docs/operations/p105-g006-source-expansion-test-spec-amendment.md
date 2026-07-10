# P105 G006 Source-Expansion Test Spec Amendment

Status: planning only. This amendment defines future RED-to-GREEN tests for the
G006 source-expansion amendment. It does not claim those tests, adapters,
harnesses, or artifacts exist.

## Future Test Files

Add or update these implementation tests:

- `tests/test_p105_source_registry_eligibility.py`
- `tests/test_p105_source_expansion_contract.py`
- `tests/test_p105_dejavu_a1_materializer.py`
- `tests/test_p105_db_pool_harness_materializer.py`
- `tests/test_p105_log_parser_materializers.py`
- `tests/test_p105_queue_harness_materializer.py`
- `tests/test_p105_deploy_harness_materializer.py`
- `tests/test_p105_release_qualified_artifacts.py`
- `tests/test_p105_release_qualified_reproducibility.py`
- `tests/test_p105_release_evidence.py`

## RED Expectations

The first test pass must fail for the intended missing behavior:

- no reviewed source registry;
- no source eligibility manifest;
- no `command_argv` and `created_at` provenance binding on all new manifests;
- no DejaVu A1 reviewed-local materializer;
- no private A1 db-connection-limit label ledger;
- no actual Apache, Hadoop, or Zookeeper parser authority;
- no isolated queue lag/backlog/dead-letter harness;
- no isolated deploy canary/config regression harness;
- no actual RabbitMQ Docker runtime attestation;
- no actual loopback `ThreadingHTTPServer` request evidence;
- no additional honest database connection-pool source or harness to repair
  A1-only held-out database coverage insufficiency;
- no `p105.database.pool.v1` actual SQLite runtime with a bounded
  `sqlite3` connection pool, `queue.Queue`, `threading.BoundedSemaphore`, and
  real SQL insert/select/update operations;
- no rejection of fabricated four-day coverage;
- no rejection of simulated, in-memory, accelerated-clock, or schedule-only
  database/queue/deploy artifacts from release counting;
- no closed schema-adapter registry in `scripts/build_p105_source_registry.py`;
- no separation between canonical artifacts and run-specific raw runtime
  attestations;
- no macro-sequence release gate that blocks P106 before independent review and
  full verification.

## Contract Tests

Required assertions:

- Source registry is required before scoring and includes every input source.
- Eligibility manifest is required before scoring and is the only counting
  authority for supported-family floors.
- Unsupported, ambiguous, parser-failed, unreviewed, or unmapped rows are
  `unsupported_family` and contribute zero rows, positives, incident groups,
  source diversity, coverage, or floor credit.
- Missing `command_argv`, `created_at`, source hash, materialized hash,
  registry hash, eligibility hash, privacy/license hash, private ledger hash,
  reviewer ID, or review timestamp fails closed.
- Existing P105 floors remain byte-for-byte equivalent in thresholds and
  formulas; tests must fail if any floor is lowered or any new source receives
  synthetic padding.
- Simulated, in-memory, accelerated-clock, schedule-only, and synthetic
  database/queue/deploy artifacts are accepted only as RED fixtures and count as zero
  release rows, positives, groups, tuples, coverage, and P106 unlock credit.
- `runtime_attestation.kind` accepts only `actual_sqlite_pool`,
  `actual_rabbitmq_docker`, and `actual_threading_http_server` for
  release-counting evidence.
- Source telemetry/manifests must not contain `release_counting_allowed`,
  `verified_release_counting`, or equivalent counting authority. They declare
  only runtime attestation kind/capability.
- `verified_release_counting=true` is honored only from a verifier-owned
  qualification receipt after the independent verifier succeeds for canonical
  artifacts, run envelopes, raw attestation hashes, runtime kind, command
  arguments, tamper fixtures, and source eligibility.
- Forged simulation kinds, missing runtime kind, unknown runtime kind, or a
  forged counting field on otherwise invalid source evidence is always
  non-counting.
- Partitions are assigned before labels join.
- Public rows cannot contain private labels, incident answer keys, label hashes
  reversible to answer keys, floor deficits, or gate outcomes.

RED negative fixtures must include:

- `runtime_attestation.kind=simulated` with a forged counting field;
- `runtime_attestation.kind=actual_sqlite_pool` but no real SQL-operation
  counters or raw attestation hash;
- `runtime_attestation.kind=actual_rabbitmq_docker` with in-memory queue rows;
- `runtime_attestation.kind=actual_threading_http_server` with materialized
  rows but no loopback handler observations;
- an unknown manifest schema passed to the source registry producer;
- canonical JSON containing raw monotonic nanoseconds, thread IDs, container
  IDs, Docker network names, or ephemeral ports.

## DejaVu A1 Tests

Required assertions:

- The A1 command accepts exactly
  `/private/tmp/opscat-dejavu-A1/A1/metrics.csv`,
  `/private/tmp/opscat-dejavu-A1/A1/faults.csv`, and
  `/private/tmp/opscat-dejavu-A1/A1/graph.yml`, or an explicit reviewed raw
  source manifest resolving to the same schema.
- `metrics.csv` and `graph.yml` feed public features before labels join.
- `faults.csv` feeds a private label ledger only.
- Only reviewed `db connection limit` records may be eligible for the
  `database` family.
- The registry records supplied license metadata as CC-BY-4.0 plus citation,
  license URL, reviewer, redistribution, privacy, and redaction fields.
- Coverage derives from actual A1 timestamps and merged intervals. Four-day
  constants, row-count duration, floor-sized intervals, and timestamp padding
  fail closed.
- A1 rows without matching public feature window, private label binding,
  source-window ID, pre-label partition, or materialized-record hash are
  unevaluable.
- Tests assert the seven reviewed A1 incidents are exactly seven and cannot be
  copied, split, retimed, or multiplied. Because A1 alone has only
  1.7513888889 held-out database service-days, release qualification requires
  an additional independently reviewed honest database connection-pool source
  or isolated harness when database remains supported.

## Database Pool Source Tests

Required assertions:

- A reviewed raw database source or `p105.database.pool.v1` isolated harness
  supplies the additional database coverage; no new micro-ticket is created.
- `p105.database.pool.v1` is implemented only as
  `scripts/run_p105_db_pool_harness.py` using dependency-free Python standard
  library `sqlite3`, `queue.Queue`, `threading.BoundedSemaphore`, `threading`,
  `time`, `hashlib`, and `json`; it must not use an in-memory SQLite database,
  mocked connection, precomputed row generator, app runtime dependency,
  credential lookup, network call, or production data.
- The fixed command includes `--sqlite-db`, `--seed 105028`, all eight service
  IDs, explicit held-out and shadow service sets, `--pool-size 3`,
  `--workers-per-service 12`, `--acquisitions-per-worker-per-second 1`,
  `--acquire-timeout-ms 75`, `--normal-hold-ms 20`,
  `--saturation-hold-ms 650`, `--ticks 7200`, `--tick-seconds 1`,
  `--mode isolated-local`, `--created-at 2024-03-09T16:13:20Z`,
  `--expect-runtime-attestation-kind actual_sqlite_pool`, and
  `--expect-no-production-authority`.
- Partition is assigned before private schedule loading:
  `dbpool-svc-00..dbpool-svc-03 -> held_out_test` and
  `dbpool-svc-04..dbpool-svc-07 -> real_derived_shadow`.
- The private schedule is exact: saturation windows
  `600..899`, `1200..1499`, `1800..2099`, `2400..2699`, `900..1199`,
  `1500..1799`, `2100..2399`, and `2700..2999` for services
  `dbpool-svc-00` through `dbpool-svc-07`; stall windows `2100..2159`,
  `2700..2759`, `3300..3359`, `3900..3959`, `3000..3059`,
  `3600..3659`, `4200..4259`, and `4800..4859` respectively.
- Every successful public DB-pool row binds to actual SQL
  `INSERT`, `SELECT COUNT(*)`, and `UPDATE` operations through a checked-out
  `sqlite3.Connection` from the bounded pool.
- Public telemetry includes timestamped pool size, checked-out count, wait
  queue length, timeout count, acquisition latency bucket, successful and
  failed acquisition counts, partition, source-window ID, and monotonic
  observation metadata.
- Private labels come only from a reviewed `db connection limit` or
  connection-pool-saturation ledger joined after sampling and partitioning.
- Coverage is actual monotonic observation time after interval union. The
  harness may not target, truncate, pad, or synthesize exactly the A1 deficit.
- Canonical DB-pool artifacts exclude raw monotonic nanoseconds, process IDs,
  thread IDs/names, and SQLite connection object IDs; those fields may appear
  only in `p105-db-pool-runtime-attestation.raw.json`, which the runtime-phase
  verifier binds to a verifier-created envelope under the declared verification
  output directory.
- DB-pool reruns require byte-identical canonical non-raw files. Raw
  attestation hashes may differ across runs, but each run envelope must verify
  the canonical artifact root hash, raw attestation path/hash, runtime
  capability, and result.
- Missing DB-pool manifest, private ledger, coverage attestation, or reviewed
  eligibility keeps database `source_insufficient` and leaves P106 locked.

## Parser Tests

Required assertions:

- Apache, Hadoop, and Zookeeper materialization uses actual parsers with parser
  version, line offset, parsed timestamp, severity/event fields when available,
  redacted public payload, and parse status.
- Parser failure produces `unsupported_family`.
- Parser success alone does not count for deploy; a reviewed deploy/config
  regression predicate is also required.
- Family assignment cannot use source filename, ordinal row number, partition,
  release-floor deficit, private label, P105 score, P24 score, or post-incident
  values.
- Parser outputs are hash-bound to source bytes and command arguments.

## Queue Harness Tests

Required assertions:

- The queue harness is isolated local-only and produces real consumer lag or
  offset delay, backlog or queue depth, and dead-letter telemetry.
- Release-counting queue evidence must run actual RabbitMQ Docker
  `rabbitmq:3.13-management-alpine` via `tools/p105/queue/docker-compose.yml`;
  in-memory queue simulation is RED-only and non-counting.
- The harness records producer and consumer timestamps, private injected event
  IDs, injected fault windows, and a private injection ledger.
- The harness uses the fixed RabbitMQ component, seed, clock, schedule,
  producer and consumer rates, pause windows, poison-message ticks, full-census
  sampling, and partition rule from the amendment.
- The harness reads no credentials, uses no production broker endpoint, and
  performs no production mutation.
- If a Docker Compose RabbitMQ or Kafka service is used, it is harness-only and
  does not add an app runtime dependency.
- The run-specific raw attestation records container ID, image ID, RepoDigest,
  compose file hash, Docker network name, zero host ports, and
  `monotonic_started_ns`/`monotonic_finished_ns`; the canonical manifest records
  only deterministic broker observation hashes and runtime kind/capability.
- Container ID, Docker network name, raw monotonic nanoseconds, and host port
  scan details are run-specific raw attestation fields only. Canonical queue
  artifacts record deterministic semantic summaries and runtime kind/capability
  `actual_rabbitmq_docker`, but no raw attestation path/hash or counting field.
  The verifier-owned run envelope records the canonical root hash, raw
  attestation path/hash, and verification result.
- Public queue telemetry joins to private labels only after label-blind
  partitioning.
- Queue reruns are byte-identical across all canonical files, and tampering
  with telemetry, private ledger, schedule arguments, or broker digest fails
  closed.

## Deploy Harness Tests

Required assertions:

- The deploy harness is isolated local-only and records baseline and canary
  cohorts, config or version change event, request count, error rate, latency
  distribution, rollback trigger, rollback-observed timestamp, and private
  injection ledger.
- Release-counting deploy evidence must use actual loopback
  `ThreadingHTTPServer` instances and real client requests to `127.0.0.1`;
  deterministic row materialization without HTTP serving is RED-only and
  non-counting.
- The harness uses the fixed loopback component, seed, clock, traffic schedule,
  baseline/canary cohort split, fault tick, rollback oracle, full-census
  sampling, and pre-ledger partition rule from the amendment.
- The harness does not call cloud APIs, production deploy tooling, real PR
  creation, credentials, or production mutation.
- Local rollback evidence is label evidence only and never creates P106, P107,
  or production execution authority.
- Each public row binds to a server handler observation, loopback port, server
  thread identity or name, response status/body hash, measured
  `time.monotonic_ns()` latency, and monotonic duration coverage attestation.
- Loopback port, raw monotonic nanoseconds, process ID, and server thread
  identity/name are run-specific raw attestation fields only. Canonical deploy
  artifacts record deterministic semantic summaries and runtime kind/capability
  `actual_threading_http_server`, but no raw attestation path/hash or counting
  field. The verifier-owned run envelope records the canonical root hash, raw
  attestation path/hash, and verification result.
- Deploy rows count only when telemetry, private injection ledger, coverage,
  partition, and registry eligibility all bind to the same source-window ID.
- Deploy reruns are byte-identical across all canonical files, and tampering
  with telemetry, private ledger, config hash, rollback window, command
  argument, or authority counter fails closed.

## Artifact and Reproducibility Tests

Required assertions:

- New artifacts include `p105-reviewed-source-registry.json`,
  `p105-source-eligibility-manifest.json`, the additional DB-pool manifest when
  database remains supported, source-specific private ledgers, and
  source-specific reviewed-local manifests.
- Every artifact records `command_argv`, `created_at`, normalized source paths
  or manifest keys, content hashes, and provenance hashes.
- Two runs over the same inputs produce byte-identical canonical artifacts after
  normalizing allowed output directory differences. Canonical comparison
  excludes raw runtime attestations, verifier-owned run envelopes, raw
  attestation paths/hashes, and any per-run volatile-derived value.
- Raw runtime attestation files are independently SHA-256 verified per run by
  verifier-owned run envelopes. Their volatile hashes and envelope paths are
  not expected to match across runs.
- Tampering with A1 source files, parser source files, queue harness telemetry,
  deploy harness telemetry, private injection ledgers, coverage intervals,
  runtime attestation fields, partitions, command arguments, license metadata,
  or eligibility decisions fails closed.
- Synthetic four-day coverage compatibility is removed from the release path:
  any fixed four-day constant, row-count duration, top-level duration,
  floor-sized interval, or accelerated logical clock fails release counting.
- Release benchmark input excludes unsupported-family and unevaluable rows.
- Release benchmark output records locked source-insufficiency when actual
  reviewed sources miss unchanged floors.

## Registry and Materializer CLI Tests

Required assertions:

- P105-024 owns RED tests proving the central materializer and source registry
  fail before the closed schema adapters exist.
- `scripts/build_p105_source_registry.py` accepts explicit `--schema-adapter`
  flags for `p32`, `p41`, `p44`, `dejavu_a1`, `db_pool`, `queue`, and
  `deploy`; it emits normalized reviewed-source entries and fails closed on
  unknown root schema, unknown fields, missing adapter mapping, or reviewed
  ledger mismatch.
- P105-028 owns the central materializer parser and enforcement for
  `--schema-adapter`, `--fail-on-unknown-source-schema`,
  `--reject-synthetic-four-day-coverage`,
  `--require-actual-runtime-attestation`, and
  `--count-only-verified-release-receipts`.
- P105-028 owns runtime-phase verifier enforcement for rerun manifests, raw
  attestation inputs, `--write-run-envelopes-dir`,
  `--expect-byte-identical-canonical-reruns`, and `--expect-runtime-kinds`; the
  verifier creates envelopes and the source runtime qualification receipt.
- P105-028 also owns central materializer consumption of
  `--source-runtime-qualification-receipt`.
- P105-029 owns release-phase verifier enforcement for the source runtime
  receipt, release directory, final artifact hashes, and P106 gate.

## Review and Verification Tests

Required assertions:

- A plan-review artifact must be recorded before RED tests are considered
  complete.
- Independent code review and architecture review are required after actual
  source runs and release benchmark, not before.
- Full verification evidence includes targeted source-expansion tests, existing
  P105-RQ tests, docs verification, fast verification, coverage gate, release
  benchmark artifact hash, and no known errors.
- P106 cannot be marked unlocked unless the complete macro sequence has passed
  and the exact P105-RQ gate payload has `release_qualified=true`.

## Acceptance Commands

Future implementation must make this command pass after first observing RED:

```bash
uv run --no-sync --extra dev pytest -q \
  tests/test_p105_source_registry_eligibility.py \
  tests/test_p105_source_expansion_contract.py \
  tests/test_p105_dejavu_a1_materializer.py \
  tests/test_p105_db_pool_harness_materializer.py \
  tests/test_p105_log_parser_materializers.py \
  tests/test_p105_queue_harness_materializer.py \
  tests/test_p105_deploy_harness_materializer.py
```

The source-expanded release run must then pass:

```bash
uv run --no-sync --extra dev python scripts/materialize_p105_dejavu_a1_reviewed_local.py \
  --metrics-csv /private/tmp/opscat-dejavu-A1/A1/metrics.csv \
  --faults-csv /private/tmp/opscat-dejavu-A1/A1/faults.csv \
  --graph-yml /private/tmp/opscat-dejavu-A1/A1/graph.yml \
  --license-name CC-BY-4.0 \
  --output-dir /tmp/opscat-p105-reviewed-dejavu-a1 \
  --review-status reviewed-local \
  --expect-source-hashes
```

```bash
SOURCE_DATE_EPOCH=1710000800 \
uv run --no-sync --extra dev python scripts/run_p105_db_pool_harness.py \
  --sqlite-db /tmp/opscat-p105-db-pool-harness/p105-database-pool.sqlite3 \
  --seed 105028 \
  --services dbpool-svc-00,dbpool-svc-01,dbpool-svc-02,dbpool-svc-03,dbpool-svc-04,dbpool-svc-05,dbpool-svc-06,dbpool-svc-07 \
  --heldout-services dbpool-svc-00,dbpool-svc-01,dbpool-svc-02,dbpool-svc-03 \
  --shadow-services dbpool-svc-04,dbpool-svc-05,dbpool-svc-06,dbpool-svc-07 \
  --pool-size 3 \
  --workers-per-service 12 \
  --acquisitions-per-worker-per-second 1 \
  --acquire-timeout-ms 75 \
  --normal-hold-ms 20 \
  --saturation-hold-ms 650 \
  --ticks 7200 \
  --tick-seconds 1 \
  --output-dir /tmp/opscat-p105-db-pool-harness \
  --mode isolated-local \
  --created-at 2024-03-09T16:13:20Z \
  --expect-runtime-attestation-kind actual_sqlite_pool \
  --expect-no-production-authority
```

```bash
SOURCE_DATE_EPOCH=1710002000 \
uv run --no-sync --extra dev python scripts/build_p105_source_registry.py \
  --candidate-manifest evals/telemetry/replay/p32_replay_pack.json \
  --candidate-manifest evals/real_datasets/raw/p41_sources.json \
  --candidate-manifest /tmp/opscat-p105-reviewed-p44/p44-reviewed-local-manifest.json \
  --candidate-manifest /tmp/opscat-p105-reviewed-dejavu-a1/p105-dejavu-a1-reviewed-local-manifest.json \
  --candidate-manifest /tmp/opscat-p105-db-pool-harness/p105-db-pool-harness-manifest.json \
  --candidate-manifest /tmp/opscat-p105-queue-harness/p105-queue-harness-manifest.json \
  --candidate-manifest /tmp/opscat-p105-deploy-harness/p105-deploy-harness-manifest.json \
  --schema-adapter p32=p105.adapter.p32-replay.v1 \
  --schema-adapter p41=p105.adapter.p41-sources.v1 \
  --schema-adapter p44=p105.adapter.p44-reviewed-local.v1 \
  --schema-adapter dejavu_a1=p105.adapter.dejavu-a1-reviewed-local.v1 \
  --schema-adapter db_pool=p105.adapter.database-pool-harness.v1 \
  --schema-adapter queue=p105.adapter.rabbitmq-harness.v1 \
  --schema-adapter deploy=p105.adapter.threading-http-deploy-harness.v1 \
  --review-ledger /tmp/opscat-p105-source-expansion/p105-source-review-ledger.json \
  --output-registry /tmp/opscat-p105-source-expansion/p105-reviewed-source-registry.json \
  --output-eligibility /tmp/opscat-p105-source-expansion/p105-source-eligibility-manifest.json \
  --created-at 2024-03-09T16:33:20Z \
  --schema-version p105.source-registry.v1 \
  --fail-on-unknown-source-schema \
  --fail-on-unreviewed-counting-source
```

```bash
UV_CACHE_DIR=/private/tmp/opscat-uv-cache \
uv run --no-sync --extra dev python scripts/verify_p105_source_expansion_artifacts.py \
  --phase runtime \
  --registry /tmp/opscat-p105-source-expansion/p105-reviewed-source-registry.json \
  --eligibility /tmp/opscat-p105-source-expansion/p105-source-eligibility-manifest.json \
  --db-pool-manifest /tmp/opscat-p105-db-pool-harness/p105-db-pool-harness-manifest.json \
  --db-pool-rerun-manifest /tmp/opscat-p105-db-pool-harness-rerun/p105-db-pool-harness-manifest.json \
  --db-pool-raw-attestation /tmp/opscat-p105-db-pool-harness/p105-db-pool-runtime-attestation.raw.json \
  --db-pool-rerun-raw-attestation /tmp/opscat-p105-db-pool-harness-rerun/p105-db-pool-runtime-attestation.raw.json \
  --queue-manifest /tmp/opscat-p105-queue-harness/p105-queue-harness-manifest.json \
  --queue-rerun-manifest /tmp/opscat-p105-queue-harness-rerun/p105-queue-harness-manifest.json \
  --queue-raw-attestation /tmp/opscat-p105-queue-harness/p105-queue-runtime-attestation.raw.json \
  --queue-rerun-raw-attestation /tmp/opscat-p105-queue-harness-rerun/p105-queue-runtime-attestation.raw.json \
  --deploy-manifest /tmp/opscat-p105-deploy-harness/p105-deploy-harness-manifest.json \
  --deploy-rerun-manifest /tmp/opscat-p105-deploy-harness-rerun/p105-deploy-harness-manifest.json \
  --deploy-raw-attestation /tmp/opscat-p105-deploy-harness/p105-deploy-runtime-attestation.raw.json \
  --deploy-rerun-raw-attestation /tmp/opscat-p105-deploy-harness-rerun/p105-deploy-runtime-attestation.raw.json \
  --write-run-envelopes-dir /tmp/opscat-p105-source-runtime-verification/envelopes \
  --output-json /tmp/opscat-p105-source-runtime-verification/p105-source-runtime-qualification.json \
  --expect-byte-identical-canonical-reruns \
  --expect-tamper-fixtures-fail-closed \
  --expect-runtime-kinds actual_sqlite_pool,actual_rabbitmq_docker,actual_threading_http_server
```

```bash
uv run --no-sync --extra dev python scripts/materialize_p105_release_evidence.py \
  --p32-replay evals/telemetry/replay/p32_replay_pack.json \
  --p41-sources evals/real_datasets/raw/p41_sources.json \
  --p44-reviewed-local-manifest /tmp/opscat-p105-reviewed-p44/p44-reviewed-local-manifest.json \
  --dejavu-a1-reviewed-local-manifest /tmp/opscat-p105-reviewed-dejavu-a1/p105-dejavu-a1-reviewed-local-manifest.json \
  --db-pool-harness-manifest /tmp/opscat-p105-db-pool-harness/p105-db-pool-harness-manifest.json \
  --queue-harness-manifest /tmp/opscat-p105-queue-harness/p105-queue-harness-manifest.json \
  --deploy-harness-manifest /tmp/opscat-p105-deploy-harness/p105-deploy-harness-manifest.json \
  --schema-adapter p32=p105.adapter.p32-replay.v1 \
  --schema-adapter p41=p105.adapter.p41-sources.v1 \
  --schema-adapter p44=p105.adapter.p44-reviewed-local.v1 \
  --schema-adapter dejavu_a1=p105.adapter.dejavu-a1-reviewed-local.v1 \
  --schema-adapter db_pool=p105.adapter.database-pool-harness.v1 \
  --schema-adapter queue=p105.adapter.rabbitmq-harness.v1 \
  --schema-adapter deploy=p105.adapter.threading-http-deploy-harness.v1 \
  --source-registry /tmp/opscat-p105-source-expansion/p105-reviewed-source-registry.json \
  --source-eligibility /tmp/opscat-p105-source-expansion/p105-source-eligibility-manifest.json \
  --output-dir /tmp/opscat-p105-release-qualified \
  --mode release_qualified \
  --reject-synthetic-four-day-coverage \
  --require-actual-runtime-attestation \
  --fail-on-unknown-source-schema \
  --source-runtime-qualification-receipt /tmp/opscat-p105-source-runtime-verification/p105-source-runtime-qualification.json \
  --count-only-verified-release-receipts
```

```bash
uv run --no-sync --extra dev python scripts/run_failure_forecast_benchmark.py \
  --release-benchmark /tmp/opscat-p105-release-qualified/p105-release-qualified-rows.json \
  --output-json /tmp/opscat-p105-release-qualified/p105-release-qualified-benchmark.json
```

```bash
bash scripts/verify.sh --profile docs
bash scripts/verify.sh --profile fast
```

Documentation-only validation for this amendment:

```bash
git diff --check
UV_CACHE_DIR=/private/tmp/opscat-uv-cache bash scripts/verify.sh --profile docs
```

Future final verification is the complete ordered sequence in this section:
registry -> runtime-phase verification/receipt -> materializer -> benchmark ->
the exact test and release-phase blocks below. No stage may be skipped:

```bash
UV_CACHE_DIR=/private/tmp/opscat-uv-cache \
uv run --no-sync --extra dev pytest -q \
  tests/test_p105_source_registry_eligibility.py \
  tests/test_p105_source_expansion_contract.py \
  tests/test_p105_dejavu_a1_materializer.py \
  tests/test_p105_db_pool_harness_materializer.py \
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
UV_CACHE_DIR=/private/tmp/opscat-uv-cache uv run --no-sync --extra dev pytest -q
```

```bash
UV_CACHE_DIR=/private/tmp/opscat-uv-cache \
uv run --no-sync --extra dev python scripts/verify_p105_source_expansion_artifacts.py \
  --phase release \
  --registry /tmp/opscat-p105-source-expansion/p105-reviewed-source-registry.json \
  --eligibility /tmp/opscat-p105-source-expansion/p105-source-eligibility-manifest.json \
  --dejavu-manifest /tmp/opscat-p105-reviewed-dejavu-a1/p105-dejavu-a1-reviewed-local-manifest.json \
  --source-runtime-qualification-receipt /tmp/opscat-p105-source-runtime-verification/p105-source-runtime-qualification.json \
  --release-dir /tmp/opscat-p105-release-qualified \
  --expect-verified-release-counting-receipt \
  --expect-db-pool-command-args \
  --output-json /tmp/opscat-p105-release-qualified/p105-artifact-hash-verification.json
```

```bash
UV_CACHE_DIR=/private/tmp/opscat-uv-cache \
uv run --no-sync --extra dev python scripts/run_failure_forecast_benchmark.py \
  --release-benchmark /tmp/opscat-p105-release-qualified/p105-release-qualified-rows.json \
  --output-json /tmp/opscat-p105-release-qualified/p105-release-qualified-benchmark.json
```

```bash
UV_CACHE_DIR=/private/tmp/opscat-uv-cache \
uv run --no-sync --extra dev python scripts/coverage_gate.py \
  --json-output /tmp/opscat-p105-release-qualified/p105-coverage-gate.json
```

```bash
UV_CACHE_DIR=/private/tmp/opscat-uv-cache bash scripts/verify.sh --profile docs
UV_CACHE_DIR=/private/tmp/opscat-uv-cache bash scripts/verify.sh --profile fast
UV_CACHE_DIR=/private/tmp/opscat-uv-cache bash scripts/verify.sh --profile full
```

## Stop Conditions

Stop if any test permits heuristic family authority, unsupported-family floor
credit, synthetic coverage, label leakage, post-label partitioning, source
padding, missing provenance binding, missing registry review, missing private
ledger, simulated/in-memory/accelerated database, queue, or deploy release
credit, forged source counting field, missing actual SQLite pool
attestation, missing actual RabbitMQ Docker attestation, missing actual
loopback `ThreadingHTTPServer` attestation, volatile runtime fields serialized
into canonical byte-identity files, production mutation, credential reads,
nonlocal broker/deploy authority, self-review, or P106 unlock before full
verification.
