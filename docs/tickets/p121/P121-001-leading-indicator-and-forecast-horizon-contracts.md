# P121-001: leading indicator and forecast horizon contracts

## Goal

Define local contracts for leading indicators and forecast horizons with
expiry, useful lead time, uncertainty, calibration buckets, OOD status,
recurrence refs, evidence refs, frozen config hashes, and exact-zero authority
snapshots.

## Contract

- Define leading indicator records with source ID, system ID, service ID,
  observed/window timestamps, signal family, signal name, normalized value,
  baseline ref, deviation score, trend ref, seasonality ref, optional
  deploy/config/topology/recurrence refs, missingness status, data quality
  status, evidence IDs, artifact hash, and authority counter snapshot.
- Define forecast records with indicator IDs, failure mode, incident family,
  probability, calibrated probability, calibration bucket, confidence
  interval, horizon start/end, minimum useful lead time, expiry, expected
  impact, uncertainty reasons, OOD status, abstention status, required
  evidence before action, model/rule version, frozen config hash, and artifact
  hash.
- Reject future labels, hidden scorer fields, post-intervention telemetry,
  post-incident hindsight, consumed holdout data, stale telemetry, unresolved
  duplicate lineage, ambiguous system identity, and missing artifact hashes.
- Prevent recurrence-derived indicators from becoming action authority without
  fresh current evidence.

## Acceptance

Forecasts cannot become intervention candidates without positive useful lead
time, an unexpired horizon, acceptable calibration status, acceptable OOD
status, required evidence refs, frozen config hash, and exact-zero authority
snapshot. Invalid horizons, expired forecasts, low-calibration forecasts,
high-OOD forecasts, post-cutoff evidence, and recurrence-only evidence route to
`investigate_more` or abstain.

## Stop Rules

Stop if indicators can include hindsight or hidden holdout data, if forecast
confidence can authorize action by itself, if expired or low-lead-time
forecasts can proceed, if calibration/OOD status is missing, or if the contract
adds auth, credentials, live connectors, production/staging mutation, L4+
authority, shell/subprocess execution, free-form action execution, or nonzero
authority counters.
