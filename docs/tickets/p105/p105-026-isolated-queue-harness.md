# P105-026 - Isolated Local Queue Harness

## Goal

Add queue-family real-derived evidence from an isolated local harness that
produces real consumer lag, backlog, and dead-letter telemetry plus a private
injection ledger.

## Scope

- future queue harness command and manifest
- private queue injection ledger
- source registry and eligibility manifest integration
- no production broker, no credentials, no app runtime dependency unless
  unavoidable

## Tests First

- Observe RED from P105-024 for missing queue harness behavior.
- Tests must prove production broker endpoints, credential reads, and
  production mutation are blocked.

## Implementation Notes

- Prefer the lightest repo-compatible local approach. A standard-library local
  process/file/socket harness is preferred if it emits real lag/backlog/dead
  letter telemetry.
- If RabbitMQ or Kafka is needed, use an isolated local Docker Compose service
  only for the harness and do not add a new application dependency.
- Private injected event IDs and fault windows join only after label-blind
  partitioning.

## Acceptance

- Harness manifest records consumer lag or offset delay, backlog or queue
  depth, dead-letter count, producer timestamps, consumer timestamps, private
  injection ledger hash, source hashes, `command_argv`, and `created_at`.
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
uv run --no-sync --extra dev python scripts/run_p105_queue_harness.py \
  --output-dir /tmp/opscat-p105-queue-harness \
  --mode isolated-local \
  --expect-no-production-authority
```

## Stop Condition

Stop if queue evidence depends on a production broker, credentials, external
network access, synthetic queue labels, post-label partitioning, missing
dead-letter telemetry, or a new app dependency that was not proven unavoidable.
