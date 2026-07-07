# P17-006 — Report and verification integration

Status: DONE

## Goal

Report and verification integration for the P17 LLM policy calibration layer.

## Acceptance Criteria

- Preserves the no-auth/local-mock boundary.
- Adds no default external model/API calls.
- Adds no action execution or production mutation.
- Is covered by targeted tests and release evidence.

## Verification

- Targeted P17 tests.
- Provider evaluation smoke in mock mode.
- Full verification gate before completion.
