# P123-001: read-only telemetry artifact intake contract

## Goal

Define the future contract for ingesting real telemetry exports, redacted
snapshots, and recorded streams as read-only artifacts.

## Contract

- Require source label, schema version, timestamp model, provenance, redaction
  metadata, and hash manifest.
- Reject credentials, secrets, live endpoints, staging targets, production
  targets, and mutation fields.
- Emit intake receipts with accepted, rejected, malformed, and dropped counts.

## Acceptance

Future implementation can validate artifact intake without credentials or live
connector calls and can fail closed with actionable errors.

## Stop Rules

Stop if intake requires credentials, calls live connectors, accepts secret
material, hides provenance gaps, or permits staging/production mutation.

