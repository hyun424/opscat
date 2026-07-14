# P137-003 - Correlated incident state

## Scope

Implement durable incident state and deterministic correlation over validated
P137 evidence atoms and P136 rejection metadata.

## Acceptance

- Correlation uses only system ID, entity hash, overlapping time window,
  provider/signal family, label hash, content hash, and P136 rejection reason.
- Free-form text similarity, embeddings, provider lookup, network lookup,
  operator prompts, regex discovery, and path discovery are impossible.
- Incident statuses follow the legal transition graph and terminal states never
  transition.
- Restart duplicate ingest preserves stable incident IDs and does not duplicate
  evidence atoms; duplicate counts are derived from repeated promotion keys and
  entry hashes.
- Open-incident, window, duration, journal, and ledger budgets fail closed.
