# P119-006: war-room timeline, operator controls, and escalation

## Goal

Define the local war-room read model, append-only timeline, operator control
events, escalation payloads, redaction rules, export behavior, and replay links
for fixture-only incidents.

## Contract

- Render current state, severity, fixture, impact, hypotheses, evidence,
  missing evidence, contradictions, selected decision, approval state,
  operation state, validation, rollback, budgets, authority counters, terminal
  status, and replay refs.
- Include every required P119 timeline event class from detection through
  terminalization, crash recovery, orphan inventory, and authority snapshots.
- Keep approval, rejection, pause, resume, abort, escalation acknowledgement,
  timeline export, and replay-link controls as local/mock metadata because auth
  is deferred.
- Redact credentials, secrets, production target strings, staging target
  strings, shell text, subprocess commands, connector payloads, external URLs,
  and untrusted model command text.
- Hash-chain timeline events and derive the war-room view from WAL receipts.

## Acceptance

War room state is replayable, redaction blocks unsafe payloads, escalation
payloads include missing evidence, contradictions, risk, validation, rollback,
budgets, counters, timeline refs, and replay refs, and operator controls cannot
introduce auth or production authority.

## Stop Rules

Stop if the war room displays secrets, credentials, production targets,
commands, connector payloads, hidden mutation instructions, unredacted model
commands, nonlocal authority, irreversible controls, or production-operation
claims.
