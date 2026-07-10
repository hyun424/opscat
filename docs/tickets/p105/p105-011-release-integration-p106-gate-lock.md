# P105-011 - Release Integration and P106 Gate Lock

## Goal

Wire P105 verification into the release workflow and make the P106 unlock
condition explicit, machine-checkable, and default-false.

## Tests First

- Release gate test verifies `p106_unlocked=false` before benchmark evidence is
  present.
- Held-out gate test verifies P106 stays blocked when Brier or ECE does not
  improve over the P24 baseline.
- Lead-time gate test verifies P106 stays blocked when any supported family with
  positives has useful lead-time rate below `0.80`.
- Zero-positive gate test verifies a supported family with
  `actual_positive_count=0` is `unevaluable` and keeps P106 locked unless the
  family is removed from `supported_families`.
- Transfer gate test verifies P106 stays blocked when real-derived shadow
  transfer fails useful lead-time, false-alert, or abstention thresholds.
- Missing-denominator gate test verifies any absent numerator, denominator,
  service-day count, family count, incident count, or abstention count fails
  closed.
- Docs guard test verifies no P106 implementation summary can claim unlock
  without the P105 gate payload.

## Implementation Notes

- Gate payload should include held-out metric pass/fail, real-derived transfer
  pass/fail, false-alert burden, abstention rate, and safety counters.
- Gate payload rows are exact:
  - held-out `p24_brier - p105_brier > 0.0000`;
  - held-out `p24_ece - p105_ece > 0.0000`;
  - useful lead-time rate `>= 0.80` per supported family with positives;
  - zero-positive supported families marked `unevaluable_zero_positive=true`;
  - false alerts/service-day `<= 0.25` globally and `<= 0.50` per family;
  - abstention rate `<= 0.20` globally and `<= 0.30` per family;
  - directional real-derived useful-lead-time transfer
    `held_out_useful_lead_time_rate - real_derived_useful_lead_time_rate <=
    0.10`, using `useful_true_positive_count / true_positive_count` for each
    split, with real-derived rate still `>= 0.80`;
  - real-derived false-alert increase `<= 0.10` and still within the
    false-alert threshold;
  - safety boundary counters remain false for auth, production mutation,
    remediation execution, executable action plans, and default external model
    calls.
- If the gate fails, the release summary must explicitly stop at shadow
  forecasting.
- Do not create production mutation paths, auth paths, or remediation executors.

## Acceptance

- P106 is blocked by default.
- P106 unlock requires held-out calibration pass and real-derived transfer pass.
- P106 unlock requires every supported family to pass its per-family rows; global
  averages cannot hide family failure.
- Missing denominators, zero-positive supported families, duplicate-alert
  burden, excessive abstention, or transfer drift keep `p106_unlocked=false`.
- Gate failure produces a clear shadow-forecasting stop condition.

## Verification

Run P105 release integration tests, docs guard tests, and the local verification
profile after implementation.
