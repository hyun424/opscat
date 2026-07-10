# P105-027 - Isolated Deploy Canary and Config Regression Harness

## Goal

Add deploy-family real-derived evidence from an isolated local canary/config
regression harness with measurable error, latency, rollback, and private
injection-ledger telemetry.

## Scope

- future deploy harness command and manifest
- private deploy injection ledger
- source registry and eligibility manifest integration
- no production deploy tooling, no cloud API, no credentials, no real PR

## Tests First

- Observe RED from P105-024 for missing deploy harness behavior.
- Tests must prove production mutation, credential reads, real PR creation, and
  cloud/deploy API calls are blocked.

## Implementation Notes

- The harness models baseline and canary cohorts locally.
- It uses fixed program `p105.deploy.canary.v1`: seed `105027`,
  `SOURCE_DATE_EPOCH=1710001400`, 1,200 one-second ticks, 10 requests per tick,
  baseline slots 0..7, canary slots 8..9, fault tick 300, canary `config-v2-bad`
  at 80 ms, and every fourth canary request returning HTTP 503.
- It emits config or version change events, request count, measured error rate,
  measured latency buckets, rollback trigger, and rollback-observed timestamp.
- Sampling is a full census of completed request observations. Partition is
  assigned before private-ledger load by hashing `request_id` with
  `p105.deploy.partition.v1`.
- Local rollback is label evidence only. It never grants action authority.

## Acceptance

- Deploy harness manifest records telemetry, coverage intervals, private ledger
  hash, source-window IDs, partition IDs, source hashes, `command_argv`, and
  `created_at`.
- Canonical outputs include public telemetry, private injection ledger,
  pre-label partitions, rollback evidence, actual coverage, harness manifest,
  and provenance hashes under `/tmp/opscat-p105-deploy-harness`.
- Rerun outputs under `/tmp/opscat-p105-deploy-harness-rerun` are
  byte-identical, and tamper checks over telemetry, ledger, config hash,
  rollback window, command argument, and authority counter fail closed.
- Rows count only when registry eligibility binds the public telemetry and
  private injected labels after pre-label partitioning.
- Authority counters remain zero for production mutation, action execution,
  cloud API calls, credential reads, and real PR creation.

## Acceptance Commands

```bash
uv run --no-sync --extra dev pytest -q \
  tests/test_p105_deploy_harness_materializer.py \
  tests/test_p105_source_registry_eligibility.py
```

Future harness command:

```bash
SOURCE_DATE_EPOCH=1710001400 \
uv run --no-sync --extra dev python scripts/run_p105_deploy_canary_harness.py \
  --host 127.0.0.1 \
  --seed 105027 \
  --ticks 1200 \
  --tick-seconds 1 \
  --requests-per-tick 10 \
  --fault-tick 300 \
  --output-dir /tmp/opscat-p105-deploy-harness \
  --mode isolated-local \
  --created-at 2024-03-09T16:23:20Z \
  --expect-rollback-trigger-tick 369 \
  --expect-rollback-observed-tick 370 \
  --expect-no-production-authority
```

## Stop Condition

Stop if deploy evidence touches production deploy tooling, cloud APIs,
credentials, real PRs, production mutation, synthetic labels, fabricated
coverage, or rollback/action authority beyond local evidence generation.
