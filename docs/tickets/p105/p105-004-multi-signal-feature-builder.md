# P105-004 - Multi-Signal Feature Builder

## Goal

Extract forecast features from P24/P25 trend windows and P104-qualified evidence
without hiding missingness or unavailable evidence.

## Tests First

- Feature extraction test covers trend slope, threshold distance, baseline
  ratio, volatility, seasonality proxy, saturation pressure, deploy/config
  change proximity, and cross-service correlation.
- Evidence-state test proves valid absence and unavailable telemetry remain
  separate feature values.
- Provenance test proves every feature records source IDs and whether it came
  from a trend window, P104 evidence envelope, replay source, or derived
  aggregate.
- Missingness test proves critical missing features trigger abstention metadata
  rather than confident imputation.

## Implementation Notes

- Consume P24/P25 `TrendWindow` data and P104 evidence envelope IDs.
- Reuse source-native windows from telemetry replay where available.
- Keep features deterministic and serializable for benchmark replay.

## Acceptance

- Feature rows include values, missingness flags, provenance, and split ID.
- No feature reads future labels, action plans, or post-incident outcomes.
- Missing critical features are visible to P105-006 abstention logic.

## Verification

Run targeted feature-builder tests with P25 fixtures, P104 valid-absence versus
unavailable cases, and real-derived replay windows.
