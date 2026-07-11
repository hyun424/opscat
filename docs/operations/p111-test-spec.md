# P111 test specification

## Unit tests

- Diagnostic views are deterministic and contain candidate-visible fields only.
- Every derived feature binds back to valid P110 evidence IDs.
- Zero/negative/large baselines produce finite bounded scores.
- P111 cache keys differ from P110 and change with prompt/config/packet changes.
- Strict output validation, action limits, and raw-response replay remain active.

## Integration tests

- Development, validation, blind, and reserve repetitions cannot be confused.
- Freeze manifests reject post-freeze prompt, model, decoding, implementation,
  packet, or source changes.
- Batch merge recomputes packets and exact raw-response replay before scoring.
- No scorer truth enters provider prompts or candidate artifacts.

## Benchmark tests

- Report paired P110/P111 metrics on the same sealed case set.
- Report per-fault, per-service, confidence calibration, paired deltas, and
  bootstrap intervals.
- Treat repetition 5 as contaminated and repetition 3 as one-time blind.
- Preserve repetition 4 as untouched reserve.

## Safety gates

All P110 safety counters remain exactly zero and no code path obtains execution
authority.
