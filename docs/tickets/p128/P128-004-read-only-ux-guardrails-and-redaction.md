# P128-004: read-only UX guardrails and redaction

## Goal

Plan read-only UX guardrails and redaction visibility.

## Contract

The UX has no mutation controls and marks redacted, missing, or unsafe fields.

## Acceptance

Future operators can inspect evidence without exposing secrets.

## Stop Rules

Stop on hidden mutation controls, secret exposure, or credential prompts.

