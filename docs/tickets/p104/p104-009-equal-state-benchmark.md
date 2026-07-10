# P104-009 - Equal-State Benchmark

## Goal

Compare P104 with P103, P101 heuristic, fixed-tool, and no-action/control arms
from identical initial lab states. Measure sufficiency quality, false handoffs,
recovery retention, gap quality, and safety counters.

## Tests First

- All arms for the same case/seed share one initial fingerprint.
- Report separates first-tool accuracy, relevant-tool discovery, sufficiency
  precision, action-ready handoff, gap quality, and downstream recovery.
- Partial/conflicting cases show lower false-remediation handoff than P103.
- Valid-case recovery is not reduced by more than two percentage points.
- Hard counters for scorer leakage, repeated tools, mutating diagnostics,
  provider action execution, production mutation, unknown tools, and state
  mismatch are zero.

## Implementation Notes

- Reuse P103 benchmark shape where possible, but add P104-specific partial and
  conflicting fixture slices.
- Count "valid absence" separately from "unavailable/no data."
- Report deterministic mock separately from optional live provider results.

## Acceptance

- P105 stop gate is satisfied only when absence/unavailability distinction and
  contradiction blocking are proven.
- Benchmark results are reproducible from seeds and fixture IDs.

## Verification

Run targeted P104 benchmark tests and the offline CLI smoke.
