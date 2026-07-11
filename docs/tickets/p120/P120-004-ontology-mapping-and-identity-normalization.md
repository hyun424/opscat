# P120-004: ontology mapping and identity normalization

## Goal

Map heterogeneous source labels, service identities, topology references,
root-cause labels, evidence classes, action families, outcomes, validation
probes, rollback probes, and authority classes into canonical OpsCat ontology
records.

## Contract

- Define mapping records with mapping ID, source label, source context,
  canonical label, mapping confidence, ambiguity set, human-review
  requirement, evidence refs, ontology version, split, system ID, and source
  hash.
- Preserve source-specific labels separately from mapped canonical labels.
- Treat ontology mapping quality as a release metric per source, system,
  incident family, and action family.
- Route ambiguous mappings to confidence penalties, investigate-more,
  abstention, escalation, or fail-closed outcomes.
- Prevent production-like or mutation-like targets from being normalized into
  safe local fixture targets.

## Acceptance

Every mapping has confidence, ambiguity set, evidence refs, ontology version,
source hash, system ID, and split. Ambiguous mappings are never coerced into
confident action paths. Mapping metrics are reported per system, source, and
family.

## Stop Rules

Stop if source labels leak hidden answers, ontology mappings force ambiguity
into action selection, action-family or outcome labels are mismapped without
visibility, or authority/mutation targets can be normalized into fixture-safe
targets.
