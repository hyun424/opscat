# P117-004: utility, calibration, and abstention policy

## Goal

Define the calibrated utility model and abstention rules that decide when an
action is beneficial enough to select from the frozen action-pack catalog.

## Contract

- Compute expected utility from P116 measured benefit versus no-action minus
  expected harm, uncertainty penalty, contradiction penalty, missing-evidence
  penalty, and authority penalty.
- Preserve numerator, denominator, nullable value, interval, scenario family,
  action family, split, and artifact hash for every utility component.
- Calibrate confidence overall and per scenario family.
- Treat `act`, `investigate_more`, `no_action`, `escalate`, and `abstain` as
  first-class labels.
- Force abstention or non-action when prerequisites are incomplete,
  contraindications are present, confidence is low, utility crosses zero,
  measured outcomes are absent, or authority counters are nonzero.

## Acceptance

Calibration ECE is <= 0.05 overall and <= 0.08 per family, contraindication
avoidance is 1.0, prerequisite compliance is 1.0, abstention precision and
recall are both >= 0.90 on abstain-required cases, and no positive action is
selected when its utility interval crosses zero.

## Stop Rules

Stop if missing denominators are coerced to success, natural recovery is
credited as action utility, or low-confidence/high-harm cases can still act.
