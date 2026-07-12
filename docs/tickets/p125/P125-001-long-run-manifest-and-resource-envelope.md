# P125-001: long-run manifest and resource envelope

## Goal

Define the future manifest for long-running shadow runs.

## Contract

- Record duration, event volume, replay source, input hashes, hardware
  context, resource limits, and scope.
- Reject aggregate-only endurance claims.
- Keep all inputs local/sandbox/replay scoped.

## Acceptance

Future long-running reports can be interpreted with clear denominators and
resource context.

## Stop Rules

Stop if run evidence omits duration, event counts, hardware context, or scope
limitations.

