# P120-001: dataset source governance and import registry

## Goal

Define source manifests, governance validation, lineage tracking, artifact
hashes, redaction receipts, split eligibility, holdout eligibility, and
exact-zero authority receipts for all P120 datasets and sources.

## Contract

- Define governance manifests for source ID, source type, license or usage
  basis, collection method, allowed use, privacy redaction status, system ID,
  dataset origin, time range, telemetry modalities, topology availability,
  labels, outcomes, actions, known biases, known duplicates, near-duplicate
  fingerprint, split eligibility, holdout eligibility, authority boundary
  receipt, and artifact hash.
- Keep public benchmark records, generated fixtures, local lab outputs,
  read-only telemetry exports, and manually curated examples separately typed.
- Preserve original source labels separately from mapped ontology labels.
- Preserve missing labels, outcomes, and actions as nullable,
  denominator-visible fields.
- Track source lineage so generated examples cannot leak into unseen holdouts
  through paraphrase, topology copy, action-pack reuse, or outcome-window reuse.

## Acceptance

Ungoverned, unlicensed, hashless, provenance-missing, authority-receipt-missing,
credential-bearing, secret-bearing, production-target-bearing,
mutation-bearing, or unclear-lineage sources fail closed. Source manifests are
included in frozen release evidence.

## Stop Rules

Stop if a source can enter evaluation without provenance, license or usage
basis, artifact hash, authority receipt, redaction status, system ID, or clear
lineage, or if source intake creates auth, credentials, production access, live
connector calls, connector writes, or mutation authority.
