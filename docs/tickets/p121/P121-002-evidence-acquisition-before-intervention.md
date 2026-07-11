# P121-002: evidence acquisition before intervention

## Goal

Define prevention evidence planning and acquisition before any recommendation,
dry-run, or L3 local sandbox attempt.

## Contract

- Attach required evidence IDs to every preventive decision or record an
  explicit `investigate_more` or `abstain_fail_closed` reason.
- Limit evidence requests to local/mock read-only sources from a frozen
  taxonomy.
- Require evidence artifact hashes, temporal cutoffs, source refs, authority
  counter snapshots, and contradiction status.
- Route missing, stale, contradictory, post-cutoff, post-intervention,
  unhashable, or nonlocal evidence to `investigate_more` or
  `abstain_fail_closed`.
- Treat evidence-bypass attempts as release-blocking fail-closed events.

## Acceptance

No preventive route can proceed without required evidence or an explicit
non-action route. Evidence acquisition remains local/mock read-only, hash-bound,
time-bounded, and denominator-visible. Evidence-bypass attempts fail closed and
are reported in release evidence.

## Stop Rules

Stop if intervention can proceed without evidence-before-action, if forecast
confidence alone can authorize action, if stale or contradictory evidence can
be ignored, if evidence acquisition reaches live connectors or credentials, or
if evidence handling creates production/staging mutation, connector writes,
shell/subprocess execution, L4+ authority, free-form action execution, or
nonzero authority counters.
