# P105-020 - Parity, Partition, Coverage, and Isolation

## Goal

Prove the qualified artifact uses actual P24 parity, outcome-neutral
partitions, merged service-day coverage, and incident-group isolation.

## Tests First

- Add RED tests proving P24 baseline rows are produced through actual P24
  `RiskSignal` and `RiskForecast` behavior.
- Add RED tests requiring per-row reconstructable P24 input parity.
- Add RED tests proving P24 and P105 metrics share the same rows, split IDs,
  families, incident matching, coverage scopes, and denominators.
- Add RED tests banning fallback to unrelated seed windows, fixture defaults,
  synthetic stand-ins, or windows with different source-window identity.
- Add RED tests proving partitions are assigned before scoring and do not use
  labels, P24/P105 scores, lead-time success, false-alert status, safety
  results, or gate status.
- Add RED tests proving each `incident_group_id` appears in exactly one
  partition.
- Add RED tests proving false-alert service days are merged interval unions per
  `split_id`/`family`/`service`/`source_system`.

## Implementation Notes

- Row-level `covered_seconds` is audit evidence only.
- Top-level coverage constants and summed overlapping row coverage cannot be
  used for false-alert burden.
- Valid supported-family rows cannot be moved to diagnostics to improve
  performance.

## Acceptance

- P24 parity is direct, current, and denominator-aligned.
- The parity manifest includes `source_window_id`, P24 input hash,
  `RiskSignal` hash, `RiskForecast` hash, and denominator alignment status.
- Partition IDs and related IDs are outcome-neutral hashes over pre-outcome
  fields plus a versioned salt.
- Incident groups are isolated across train, calibration, held-out,
  real-derived, and diagnostic partitions.
- False-alert denominators are reproducible from merged coverage intervals.

## Acceptance Commands

Future implementation must make this command pass after first observing RED:

```bash
uv run --no-sync --extra dev pytest -q \
  tests/test_p105_release_qualified_artifacts.py::test_p24_parity_partition_coverage_and_incident_isolation
```

## Stop Condition

Stop if P24 parity uses a proxy, falls back to unrelated seed windows, cannot
reconstruct row input, any incident group crosses partitions, partitioning uses
outcomes, or false-alert burden uses summed row coverage or a top-level
constant.
