# P171 Plan Review

Decision: approved for blinded staging judgment measurement with explicit sample
claim limits.

- Seal operator-confirmed outcome labels separately from agent-visible evidence.
- Compare deterministic baseline, current LLM candidate, and no-action baseline
  on the same staging episodes.
- Treat at least 30 labeled incident/precursor episodes and 200 healthy windows
  as the minimum point-estimate gate; smaller samples are informational only.
- Require separately pre-registered sample sizes for confidence-bound promotion,
  including at least 300 healthy windows for a zero-observed-false-alert 1%
  upper-bound claim.
- Report family denominators, confidence intervals, calibration, selective
  accuracy, abstention, OOD behavior, citation validity, and unsafe
  recommendation rate without hiding failed slices.
