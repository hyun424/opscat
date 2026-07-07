# P18A-004 — Rolling incident window

Status: DONE

## Goal

Rolling incident window for the P18A realtime source reader foundation.

## Acceptance Criteria

- Preserves the no-auth/local-mock boundary.
- Reads source-native inputs incrementally where applicable.
- Does not introduce external model/API calls, action execution, or production mutation.
- Has targeted tests and release evidence.

## Verification

- Targeted P18A tests.
- Realtime replay smoke in local/mock mode.
- Full verification gate before closure.
