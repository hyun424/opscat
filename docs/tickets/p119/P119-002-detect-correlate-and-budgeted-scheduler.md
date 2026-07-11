# P119-002: detect, correlate, and budgeted scheduler

## Goal

Define local fixture detection, alert deduplication, incident correlation,
resumable scheduling, retry limits, per-state budgets, expiration, pause/resume
records, and fail-closed timeout routing.

## Contract

- Accept only frozen local/mock/sandbox alert fixtures and hash-bound detection
  inputs.
- Deduplicate identical alert fingerprints into one active incident.
- Correlate near-duplicate fixture alerts without merging unrelated incidents
  or hiding recurrence.
- Track wall-clock incident budget, per-state timeout, retry limits, WAL-size
  limit, evidence budget, approval wait budget, validation window, rollback
  window, crash-recovery budget, and human escalation deadline.
- Route budget exhaustion to `investigate_more`, `escalated`, `expired`, or
  `aborted_fail_closed`; never force action because time expired.
- Append scheduler, retry, budget, expiration, pause, resume, and escalation
  receipts to the timeline.

## Acceptance

Duplicate alerts map to existing incidents, stale alert replay fails closed or
records recurrence, scheduler resumes after crash without duplicate side
effects, every budget decision is timeline-visible, and exact-zero authority
counters remain attached to all scheduler receipts.

## Stop Rules

Stop if detection reads live telemetry, calls external connectors, accepts
production or staging targets, bypasses budgets, forces action on timeout,
hides recurrence, creates duplicate active incidents for the same fingerprint,
or introduces auth, credentials, shell/subprocess, or network mutation paths.
