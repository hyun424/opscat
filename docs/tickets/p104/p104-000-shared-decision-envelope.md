# P104-000 - Shared Decision Envelope

## Goal

Define the cross-phase `EvidenceGapDecisionEnvelope` that P104 produces and
P105-P108 consume. The envelope is the only artifact that can mark evidence as
ready for downstream policy handoff.

## Tests First

- Constructor rejects missing `episode_id`, `decision_id`, `schema_version`,
  invalid route, duplicate evidence IDs, unknown evidence states, and negative
  budget counters.
- JSON round trip preserves route, requirement IDs, evidence IDs, freshness,
  provenance, trace IDs, and boundary flags.
- Public provider packet strips scorer-only fields: family, variant, split,
  expected tool, required action, harmful action, runbook answer, and outcome.
- P100 handoff adapter accepts only `sufficient_for_policy_handoff`.

## Implementation Notes

- Add frozen dataclasses or typed dictionaries in
  `app/services/evidence_gap_investigator.py`.
- Routes: `inspect_next`, `sufficient_for_policy_handoff`, `escalate_gap`,
  `abstain_fail_closed`.
- Include `read_only_tools_only=True`, `production_mutation_enabled=False`, and
  `action_authority=False` in every envelope.

## Acceptance

- Every route has a deterministic serialization.
- The envelope can represent inspect, sufficiency, escalation, and fail-closed
  outcomes without action execution.
- No public rendering exposes scorer truth.

## Verification

Run `./.venv/bin/python -m pytest tests/test_evidence_gap_investigator.py`.
