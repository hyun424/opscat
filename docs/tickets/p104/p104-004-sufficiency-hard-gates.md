# P104-004 - Sufficiency Hard Gates

## Goal

Implement deterministic sufficiency decisions with hard gates before P100 action
handoff. A positive source alone is never enough.

## Tests First

- Missing, stale, unavailable, or contradicted critical evidence blocks
  `sufficient_for_policy_handoff`.
- Optional evidence cannot override critical hard gates.
- Low telemetry coverage blocks handoff.
- Action-ready decisions cite every critical requirement ID and evidence ID.

## Implementation Notes

- Gate order should be deterministic: telemetry, critical availability,
  freshness, contradiction, source diversity, citation completeness.
- Return `inspect_next` when another useful read-only tool remains; return
  `escalate_gap` or `abstain_fail_closed` when no safe progress remains.
- Delegate to P100 only after sufficiency passes.

## Acceptance

- 100% of contradiction cases block action handoff until adjudicated or
  escalated.
- 100% of action-ready decisions cite all critical requirements.

## Verification

Run `./.venv/bin/python -m pytest tests/test_evidence_gap_investigator.py`.
