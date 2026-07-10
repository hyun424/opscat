# P104-002 - Evidence State Model

## Goal

Represent evidence state explicitly instead of treating any positive result as
action-ready. Required states: supporting, contradicting, absent, stale,
unavailable, distracting, duplicate, and not-yet-queried.

## Tests First

- Stale evidence fails a freshness-bound requirement.
- Valid absence is not the same as unavailable/no data.
- Duplicate evidence is de-duplicated by evidence ID or content fingerprint and
  counted separately.
- Any unadjudicated contradiction blocks handoff even with supporting evidence.

## Implementation Notes

- Include provenance, tool ID, collected-at timestamp or logical tick,
  freshness status, requirement IDs, and sanitized summary.
- Keep prompt-injected log text as inert evidence content.
- Make absence a valid result from a working read-only tool; make unavailable a
  capability/provider/telemetry failure.

## Acceptance

- Sufficiency logic can explain exactly which state blocked or satisfied each
  requirement.
- Reports distinguish missing evidence, valid negative evidence, stale evidence,
  and unavailable evidence.

## Verification

Run `./.venv/bin/python -m pytest tests/test_evidence_gap_investigator.py`.
