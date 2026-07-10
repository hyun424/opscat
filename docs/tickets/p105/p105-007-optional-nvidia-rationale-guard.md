# P105-007 - Optional NVIDIA Rationale Guard

## Goal

Allow opt-in NVIDIA rationale for operator explanation while ensuring provider
output never drives calibrated probability, execution confidence, or P106 gate
status.

## Tests First

- Default-run test proves model call count is zero and network is disabled.
- Provider packet test proves scorer truth, future labels, action authority,
  production credentials, and remediation capabilities are absent.
- Malformed-provider test fails closed with rationale unavailable while leaving
  deterministic forecast scores unchanged.
- Influence test proves changing provider rationale text does not alter
  probability, threshold, abstention, route, or P106 unlock status.

## Implementation Notes

- Reuse strict provider schema patterns from P104 where useful.
- Keep provider output in an `advisory_rationale` field separate from forecast
  probability and benchmark scoring.
- Require explicit opt-in flags for any live provider path.

## Acceptance

- Optional NVIDIA rationale is explanation-only.
- Provider failures do not block deterministic local/offline benchmark runs.
- Raw LLM confidence is never present in execution or P106 gate fields.

## Verification

Run targeted provider guard tests with mock malformed output and default
offline verification.
