# P128-001: replay and evidence navigation model

## Goal

Plan read-only navigation across replay runs, evidence receipts, and reports.

## Contract

Views link to immutable receipts and never call live connectors.

## Acceptance

Future UX can inspect evidence without credentials or mutation.

## Stop Rules

Stop on credential prompts, live calls, or mutation controls.

