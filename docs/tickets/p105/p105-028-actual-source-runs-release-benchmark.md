# P105-028 - Actual Source Runs and Release Benchmark

## Goal

Run the source-expanded materializer over reviewed actual sources and then run
the P105 release benchmark against only eligible rows.

## Scope

- P32/P41/P44 reviewed sources from the existing P105-RQ plan
- DejaVu A1 reviewed-local manifest
- queue harness manifest
- deploy harness manifest
- reviewed source registry
- source eligibility manifest
- release benchmark output

## Tests First

- Existing P105-RQ tests and P105-024 source-expansion tests must be GREEN
  before actual release runs.
- Negative runs must prove disabled, unreviewed, unsupported-family, and
  source-insufficient inputs remain locked.

## Implementation Notes

- Source-availability preflight runs before scoring.
- Benchmark input excludes unsupported-family and unevaluable rows.
- Coverage intervals use actual timestamps only.
- If floors are missed, publish locked source-insufficiency artifacts instead
  of fabricating coverage or labels.

## Acceptance

- Actual source run writes source registry, eligibility manifest, source
  manifests, private ledgers, partition manifest, coverage manifest, P24 parity
  manifest, provenance hashes, privacy/license/citation artifacts, and release
  benchmark payload.
- Benchmark reports exact unchanged floors, exact P106 gate rows, unsupported
  family counts, source-insufficiency status when applicable, and hard-zero
  authority counters.
- No synthetic padding, label leakage, post-label partitioning, heuristic
  family authority, production mutation, or credential read appears.

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
  tests/test_p105_release_qualified_reproducibility.py
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

## Stop Condition

Stop if actual source availability misses unchanged floors, any eligibility or
provenance artifact is missing, unsupported-family rows count, coverage is
fabricated, benchmark denominators are misaligned, or authority counters are
nonzero.
