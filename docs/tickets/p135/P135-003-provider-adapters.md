# P135-003 - Versioned provider adapters

## Deliverable

Implement Prometheus matrix, Loki streams, Grafana Classic dashboard, Sentry
top-level issue-list array, and OTLP file JSONL adapters plus one normalized
evidence record/bundle contract.

## Acceptance

- Deterministic provider-specific parsing and strict selected semantics.
- Sensitive/untrusted text is redacted, hashed, and risk flagged.
- Unknown provider fields are budget-checked then ignored; P135 schemas remain
  exact-key.
- Sentry uses a top-level issue-list array and each OTLP file is single-signal.
- Every output wraps an independently valid denominator-visible P120 record.
