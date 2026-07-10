# P105-024 - Source-Expansion RED Contract Tests

## Goal

Write the RED tests for the complete source-expansion contract before adapters,
parsers, harnesses, or release runs are implemented.

## Scope

- `tests/test_p105_source_registry_eligibility.py`
- `tests/test_p105_source_expansion_contract.py`
- `tests/test_p105_dejavu_a1_materializer.py`
- `tests/test_p105_log_parser_materializers.py`
- `tests/test_p105_queue_harness_materializer.py`
- `tests/test_p105_deploy_harness_materializer.py`

## Tests First

This ticket is tests-first by definition. The intended RED failures are:

- no reviewed source registry;
- no eligibility manifest;
- no DejaVu A1 reviewed-local materializer;
- no Apache, Hadoop, or Zookeeper parser authority;
- no isolated queue harness;
- no isolated deploy canary/config regression harness;
- no rejection of fabricated coverage;
- no macro-sequence P106 lock.

## Implementation Notes

- Tests must assert exact existing P105 floors; do not introduce new floor
  values.
- Tests must reject synthetic padding, label leakage, post-label partitioning,
  unsupported-family counting, and heuristic family authority.
- Tests should be small and contract-focused, but this ticket should not be
  split into one-test micro tickets.

## Acceptance

- Each missing implementation surface fails RED for the expected reason.
- The RED output names the missing adapter, parser, harness, manifest, or gate.
- Existing P105-RQ tests remain in scope for later GREEN verification.

## Acceptance Commands

```bash
uv run --no-sync --extra dev pytest -q \
  tests/test_p105_source_registry_eligibility.py \
  tests/test_p105_source_expansion_contract.py \
  tests/test_p105_dejavu_a1_materializer.py \
  tests/test_p105_log_parser_materializers.py \
  tests/test_p105_queue_harness_materializer.py \
  tests/test_p105_deploy_harness_materializer.py
```

## Stop Condition

Stop if tests pass without implementation, rely on synthetic fixtures as
release evidence, lower floors, or omit the non-counting unsupported-family
contract.
