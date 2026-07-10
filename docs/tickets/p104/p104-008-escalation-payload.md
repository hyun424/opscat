# P104-008 - Escalation Payload

## Goal

Standardize abstention/escalation output so an operator or later phase can see
exactly what is missing, stale, contradicted, duplicated, unavailable, or unsafe.

## Tests First

- Every abstention contains at least one actionable evidence gap.
- Contradiction payloads include supporting and contradicting evidence IDs.
- Unavailable-tool payloads name the missing capability without inventing auth
  or production connector work.
- Redaction removes secrets and treats prompt-injected instructions as data.

## Implementation Notes

- Include missing requirement IDs, evidence state summaries, attempted tools,
  blocked/unavailable capabilities, proposed next read-only capability, and
  operator-facing rationale.
- Keep payload deterministic for golden report tests.

## Acceptance

- Every non-handoff route is explainable from the payload.
- The payload does not request credentials, production access, or mutation.

## Verification

Run targeted P104 tests and release-doc secret-marker checks.
