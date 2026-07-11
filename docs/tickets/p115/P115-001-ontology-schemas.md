# P115-001: incident/action/outcome ontology and immutable schemas

Implement the P115 schema set for incidents, action packs, hidden outcome
contracts, action labels, paired scores, partition manifests, and release
evidence. Every artifact carries `schema_version`, rejects unknown major
versions, serializes deterministically, and preserves nullable values separately
from zero-valued metrics.

The ontology must represent action, no-action, investigate-more, escalation,
harm, unnecessary intervention, natural recovery, validation, rollback,
collateral damage, recurrence, and outcome attribution without exposing hidden
outcome labels to candidates.
