# P18B-002 — Judgment quality dimension expansion

Status: TODO

## Goal

Judgment quality dimension expansion for the P18B Model Judgment Quality Lab.

## Acceptance Criteria

- Preserves the no-auth/local-mock boundary.
- Separates raw model quality from P17 calibrated OpsCat quality where relevant.
- Adds no default external model/API calls, action execution, or production mutation.
- Has targeted tests and release evidence.

## Verification

- Targeted P18B tests.
- Mock model-quality smoke in normal verification.
- Optional NVIDIA live evidence only through explicit opt-in.
- Full verification gate before closure.
