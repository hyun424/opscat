# P120-003: telemetry normalization and read-only connector contracts

## Goal

Normalize heterogeneous metrics, logs, traces, events, topology, deploy/config
markers, validation signals, rollback probes, and outcome windows into
canonical evidence envelopes with read-only connector/importer contracts.

## Contract

- Define canonical telemetry envelopes with telemetry record ID, source ID,
  system ID, service ID, entity ref, modality, observed and ingested
  timestamps, window bounds, signal name, signal value, unit, severity, labels,
  topology refs, deploy/config refs, redaction receipt, normalization version,
  source hash, and authority counter snapshot.
- Preserve raw source hashes, timestamp uncertainty, clock skew, missing
  windows, delayed arrivals, duplicates, reorder events, contradictory
  readings, modality identity, units, nullable fields, redaction receipts, and
  authority receipts.
- Route missing, delayed, duplicated, reordered, contradictory, stale,
  malformed, or unsupported telemetry to explicit evidence states.
- Define read-only connector/importer contracts for supported local fixture,
  curated benchmark, and imported read-only telemetry sources.

## Acceptance

Read-only contract tests prove mutation surfaces are unreachable. Supported-load
ingestion loss is <= 0.1% or release is blocked. Malformed and stale telemetry
fails closed and remains denominator-visible. No normalized record can hide
authority drift or production-like target data.

## Stop Rules

Stop if a connector write endpoint is reachable, credentials are required,
live connector calls occur, production/staging URLs enter action paths, mutation
fields are accepted, ingestion loss exceeds the release gate, or malformed
telemetry is silently dropped from denominators.
