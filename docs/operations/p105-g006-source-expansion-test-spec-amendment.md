# P105 G006 Source-Expansion Test Spec Amendment

Status: planning only. This amendment defines future RED-to-GREEN tests for the
G006 source-expansion amendment. It does not claim those tests, adapters,
harnesses, or artifacts exist.

## Future Test Files

Add or update these implementation tests:

- `tests/test_p105_source_registry_eligibility.py`
- `tests/test_p105_source_expansion_contract.py`
- `tests/test_p105_dejavu_a1_materializer.py`
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
- no rejection of fabricated four-day coverage;
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
- Partitions are assigned before labels join.
- Public rows cannot contain private labels, incident answer keys, label hashes
  reversible to answer keys, floor deficits, or gate outcomes.

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
- The harness records producer and consumer timestamps, private injected event
  IDs, injected fault windows, and a private injection ledger.
- The harness reads no credentials, uses no production broker endpoint, and
  performs no production mutation.
- If a Docker Compose RabbitMQ or Kafka service is used, it is harness-only and
  does not add an app runtime dependency.
- Public queue telemetry joins to private labels only after label-blind
  partitioning.

## Deploy Harness Tests

Required assertions:

- The deploy harness is isolated local-only and records baseline and canary
  cohorts, config or version change event, request count, error rate, latency
  distribution, rollback trigger, rollback-observed timestamp, and private
  injection ledger.
- The harness does not call cloud APIs, production deploy tooling, real PR
  creation, credentials, or production mutation.
- Local rollback evidence is label evidence only and never creates P106, P107,
  or production execution authority.
- Deploy rows count only when telemetry, private injection ledger, coverage,
  partition, and registry eligibility all bind to the same source-window ID.

## Artifact and Reproducibility Tests

Required assertions:

- New artifacts include `p105-reviewed-source-registry.json`,
  `p105-source-eligibility-manifest.json`, source-specific private ledgers, and
  source-specific reviewed-local manifests.
- Every artifact records `command_argv`, `created_at`, normalized source paths
  or manifest keys, content hashes, and provenance hashes.
- Two runs over the same inputs produce byte-identical artifacts after
  normalizing allowed output directory differences.
- Tampering with A1 source files, parser source files, queue harness telemetry,
  deploy harness telemetry, private injection ledgers, coverage intervals,
  partitions, command arguments, license metadata, or eligibility decisions
  fails closed.
- Release benchmark input excludes unsupported-family and unevaluable rows.
- Release benchmark output records locked source-insufficiency when actual
  reviewed sources miss unchanged floors.

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
uv run --no-sync --extra dev python scripts/materialize_p105_release_evidence.py \
  --p32-replay evals/telemetry/replay/p32_replay_pack.json \
  --p41-sources evals/real_datasets/raw/p41_sources.json \
  --p44-reviewed-local-manifest /tmp/opscat-p105-reviewed-p44/p44-reviewed-local-manifest.json \
  --dejavu-a1-reviewed-local-manifest /tmp/opscat-p105-reviewed-dejavu-a1/p105-dejavu-a1-reviewed-local-manifest.json \
  --queue-harness-manifest /tmp/opscat-p105-queue-harness/p105-queue-harness-manifest.json \
  --deploy-harness-manifest /tmp/opscat-p105-deploy-harness/p105-deploy-harness-manifest.json \
  --source-registry /tmp/opscat-p105-source-expansion/p105-reviewed-source-registry.json \
  --source-eligibility /tmp/opscat-p105-source-expansion/p105-source-eligibility-manifest.json \
  --output-dir /tmp/opscat-p105-release-qualified \
  --mode release_qualified
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
bash scripts/verify.sh --profile docs
```

## Stop Conditions

Stop if any test permits heuristic family authority, unsupported-family floor
credit, synthetic coverage, label leakage, post-label partitioning, source
padding, missing provenance binding, missing registry review, missing private
ledger, production mutation, credential reads, nonlocal broker/deploy authority,
self-review, or P106 unlock before full verification.
