# P123 Adversarial Test Specification

This specification is a planning handoff for future P123 implementation.
Implementation is pending. It does not require source-code edits, test edits,
runtime access, connector access, credentials, live telemetry access, staging
access, production access, or mutation during this documentation turn.

## Contract and Authority

- Reject auth context, credentials, secrets, credential scopes, live connector
  names, live API endpoints, staging target strings, production target
  strings, connector writes, mutation fields, shell/subprocess action fields,
  free-form action prose, LLM command text, and L4+ action requests.
- Require exact-zero counters for every authority dimension listed in the
  P123 roadmap.
- Reject claims that recorded replay proves live production operation.

## Artifact Intake

- Detect missing source label, missing timestamp model, missing redaction
  metadata, missing provenance, missing hash manifest, malformed event schema,
  unsupported telemetry type, secret-bearing field, and production target
  leakage.
- Require intake to fail closed before any shadow run when provenance, hash, or
  redaction metadata is absent.

## Recorded Replay

- Detect nondeterministic playback, wall-clock dependence, live network call,
  mutable replay input, replay hash drift, event-order drift, and replay result
  without receipt.
- Require replay to emit deterministic run IDs, input hashes, event counts,
  dropped-record counts, and authority counters.

## Shadow Outputs

- Detect remediation recommendations stated as executed actions, hidden write
  reachability, live proof language, aggregate-only evidence, missing evidence
  citations, missing uncertainty, and missing replay reference.
- Require judgments to remain observational and evidence-bound.

## Named RED Cases

- `credential_required_for_shadow_attachment`
- `live_connector_call_present`
- `production_target_present`
- `staging_target_present`
- `secret_material_in_telemetry_artifact`
- `recorded_replay_claimed_as_live_proof`
- `shadow_output_implies_executed_remediation`
- `nonzero_authority_counter`
- `missing_artifact_hash_manifest`
- `missing_redaction_metadata`
- `nondeterministic_replay`

## Verification Profile

Future implementation must provide targeted P123 verification for artifact
intake, replay determinism, shadow outputs, evidence receipts, no-credential
guardrails, exact-zero authority counters, and honest local/sandbox/shadow
qualification. Documentation completion does not require those tests to exist
yet.

