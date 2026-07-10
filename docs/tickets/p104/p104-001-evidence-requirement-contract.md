# P104-001 - Evidence Requirement Contract

## Goal

Create typed `EvidenceRequirement` records for hypotheses so sufficiency can be
checked against explicit critical, optional, freshness, contradiction, and
source-diversity requirements.

## Tests First

- Critical requirements cannot be marked optional.
- Each action-ready hypothesis requires at least one critical requirement and
  one contradiction check.
- Tool candidates must exist in P101's closed read-only catalog.
- Requirement text cannot include scorer-only labels or action answers.

## Implementation Notes

- Model fields should include `requirement_id`, `hypothesis_id`,
  `source_family`, `candidate_tools`, `criticality`, `accepted_states`,
  `freshness_seconds`, `contradiction_policy`, and `rationale`.
- Keep requirements data local and deterministic; do not add production
  connector or auth scope.

## Acceptance

- Requirements are sufficient to explain why a gap is blocking.
- Later tickets can compute sufficiency and next-tool value from this contract.

## Verification

Run the targeted P104 tests after adding RED tests for validation errors.
