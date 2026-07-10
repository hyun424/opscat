# P105-011 - Release Integration and P106 Gate Lock

## Goal

Wire P105 verification into the release workflow and make the P106 unlock
condition explicit, machine-checkable, and default-false.

## Tests First

- Release gate test verifies `p106_unlocked=false` before benchmark evidence is
  present.
- Held-out gate test verifies P106 stays blocked when Brier or ECE does not
  improve over the P24 baseline.
- Lead-time gate test verifies P106 stays blocked when fewer than 80% of
  curated true positives have useful positive lead time.
- Transfer gate test verifies P106 stays blocked when real-derived shadow
  transfer fails useful lead-time, false-alert, or abstention thresholds.
- Docs guard test verifies no P106 implementation summary can claim unlock
  without the P105 gate payload.

## Implementation Notes

- Gate payload should include held-out metric pass/fail, real-derived transfer
  pass/fail, false-alert burden, abstention rate, and safety counters.
- If the gate fails, the release summary must explicitly stop at shadow
  forecasting.
- Do not create production mutation paths, auth paths, or remediation executors.

## Acceptance

- P106 is blocked by default.
- P106 unlock requires held-out calibration pass and real-derived transfer pass.
- Gate failure produces a clear shadow-forecasting stop condition.

## Verification

Run P105 release integration tests, docs guard tests, and the local verification
profile after implementation.
