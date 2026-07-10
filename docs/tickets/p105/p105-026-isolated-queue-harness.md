# P105-026 - Isolated Local Queue Harness

## Goal

Add queue-family real-derived evidence from an isolated local harness that
produces real consumer lag, backlog, and dead-letter telemetry plus a private
injection ledger.

## Scope

- future queue harness command and manifest
- private queue injection ledger
- source registry and eligibility manifest integration
- no production broker, no credentials, no app runtime dependency; RabbitMQ is
  a harness-only external component if used

## Tests First

- Observe RED from P105-024 for missing queue harness behavior.
- Tests must prove production broker endpoints, credential reads, and
  production mutation are blocked.

## Implementation Notes

- Use RabbitMQ `rabbitmq:3.13-management-alpine` from
  `tools/p105/queue/docker-compose.yml` on a private Docker network with no
  host ports. Capture image ID and RepoDigest in the registry.
- Use fixed program `p105.queue.rabbitmq.v1`: seed `105026`,
  `SOURCE_DATE_EPOCH=1710000400`, 900 one-second ticks, 20 produced messages
  per queue per tick, normal consumer rate 20, recovery rate 40, held-out pause
  ticks 120..179, shadow pause ticks 240..299, held-out poison tick 420, and
  shadow poison tick 600.
- Sampling is a full census of successful broker observations. Partition is
  pre-ledger and fixed: `p105.heldout.* -> held_out_test`,
  `p105.shadow.* -> real_derived_shadow`.
- Private injected event IDs and fault windows join only after label-blind
  partitioning.

## Acceptance

- Harness manifest records consumer lag or offset delay, backlog or queue
  depth, dead-letter count, producer timestamps, consumer timestamps, private
  injection ledger hash, source hashes, `command_argv`, and `created_at`.
- Canonical outputs include public telemetry, private injection ledger,
  pre-label partitions, actual coverage, harness manifest, and provenance
  hashes under `/tmp/opscat-p105-queue-harness`.
- Rerun outputs under `/tmp/opscat-p105-queue-harness-rerun` are byte-identical,
  and tamper checks over telemetry, ledger, schedule arguments, and broker
  digest fail closed.
- Queue rows are eligible only when telemetry, coverage, partition, private
  ledger, and source-window identity all bind.
- No live API calls, credential reads, production broker endpoints, production
  mutations, or action execution occur.

## Acceptance Commands

```bash
uv run --no-sync --extra dev pytest -q \
  tests/test_p105_queue_harness_materializer.py \
  tests/test_p105_source_registry_eligibility.py
```

Future harness command:

```bash
SOURCE_DATE_EPOCH=1710000400 \
uv run --no-sync --extra dev python scripts/run_p105_queue_harness.py \
  --compose-file tools/p105/queue/docker-compose.yml \
  --rabbitmq-image rabbitmq:3.13-management-alpine \
  --seed 105026 \
  --ticks 900 \
  --tick-seconds 1 \
  --output-dir /tmp/opscat-p105-queue-harness \
  --mode isolated-local \
  --created-at 2024-03-09T16:06:40Z \
  --expect-no-host-ports \
  --expect-no-production-authority
```

## Stop Condition

Stop if queue evidence depends on a production broker, credentials, external
network access, synthetic queue labels, post-label partitioning, missing
dead-letter telemetry, or a new app dependency that was not proven unavoidable.
