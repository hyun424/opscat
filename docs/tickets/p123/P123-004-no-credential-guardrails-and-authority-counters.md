# P123-004: no-credential guardrails and authority counters

## Goal

Define guardrails that keep P123 credential-free and read-only.

## Contract

- Reject auth context, credentials, secrets, credential scopes, live connector
  calls, connector writes, staging/production targets, and mutation fields.
- Emit exact-zero authority counters for every P123 evidence bundle.
- Fail closed on any missing or non-integer counter.

## Acceptance

Future verification blocks promotion whenever any credential, live-call, or
mutation authority counter is nonzero.

## Stop Rules

Stop if guardrails permit credentials, live connector calls, staging or
production mutation, L4+ authority, free-form action execution, or LLM command
execution.

