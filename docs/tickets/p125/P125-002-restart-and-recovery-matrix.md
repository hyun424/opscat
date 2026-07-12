# P125-002: restart and recovery matrix

## Goal

Define restart and recovery coverage for future shadow resilience tests.

## Contract

- Cover clean stop, crash, partial write, report interruption, and replay
  resume.
- Record pre-restart and post-restart receipts.
- Detect corrupt resumes, duplicate records, and hidden failures.

## Acceptance

Future evidence shows whether shadow state resumes without losing or
duplicating durable records.

## Stop Rules

Stop if restart tests require production infrastructure, credentials, live
connectors, or mutation authority.

