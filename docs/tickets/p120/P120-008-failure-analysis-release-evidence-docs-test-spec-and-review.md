# P120-008: failure analysis, release evidence, docs, test spec, and review

## Goal

Produce P120 failure analysis, mitigation backlog, release evidence, roadmap,
adversarial test spec, independent-style plan review, ticket README, ticket
files, and bounded claim language.

## Contract

- Classify failures by governance, split leakage, near-duplicate miss,
  normalization defect, ontology gap, OOD miss, calibration failure,
  abstention failure, baseline regression, action-family mismatch, P119 loop
  failure, and authority-boundary defect.
- Produce release evidence with exact hashes, denominators, per-system metrics,
  authority scan, replay receipts, baseline deltas, unresolved risks, and exact
  authority counters.
- Require independent review authored by a separate context from planner and
  implementer.
- Limit final claim to cross-system benchmark generalization readiness.
- Reject production readiness, live connector authority, production mutation,
  operator replacement, credentialed execution, and retuning on failed
  holdouts.

## Acceptance

Downstream docs include `p120-cross-system-generalization-roadmap.md`,
`p120-test-spec.md`, `p120-plan-review.md`, `docs/tickets/p120/README.md`, and
tickets P120-001 through P120-008. The test spec covers governance, splits,
duplicates, telemetry normalization, read-only connectors, ontology mapping,
OOD, calibration, abstention, baselines, frozen first score, per-system
metrics, failure analysis, independent verification, and exact authority zero.
Release evidence includes exact counters, all zero.

## Stop Rules

Stop if documentation or release evidence expands P120 into source/test work,
production authority, live connector authority, credential handling, production
or staging mutation, online policy mutation, operator replacement, self-review,
aggregate-only claims, or any claim beyond cross-system benchmark
generalization readiness.
