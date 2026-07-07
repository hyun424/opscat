# P18A-002 — Lightweight log parsers

Status: TODO

## Goal

Lightweight log parsers for the P18A realtime source reader foundation.

## Acceptance Criteria

- Preserves the no-auth/local-mock boundary.
- Reads source-native inputs incrementally where applicable.
- Does not introduce external model/API calls, action execution, or production mutation.
- Has targeted tests and release evidence.

## Verification

- Targeted P18A tests.
- Realtime replay smoke in local/mock mode.
- Full verification gate before closure.
