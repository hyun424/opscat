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
- It emits config or version change events, request count, error rate, latency
  distribution, rollback trigger, and rollback-observed timestamp.
- Local rollback is label evidence only. It never grants action authority.

## Acceptance

- Deploy harness manifest records telemetry, coverage intervals, private ledger
  hash, source-window IDs, partition IDs, source hashes, `command_argv`, and
  `created_at`.
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
uv run --no-sync --extra dev python scripts/run_p105_deploy_canary_harness.py \
  --output-dir /tmp/opscat-p105-deploy-harness \
  --mode isolated-local \
  --expect-no-production-authority
```

## Stop Condition

Stop if deploy evidence touches production deploy tooling, cloud APIs,
credentials, real PRs, production mutation, synthetic labels, fabricated
coverage, or rollback/action authority beyond local evidence generation.
