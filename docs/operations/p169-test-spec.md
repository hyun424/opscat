# P169 Test Spec

- Attach to one owner-approved staging telemetry environment through the P153
  live path and audited transport gates.
- Verify GET-only requests, exact host/path allowlists, HTTPS, no redirects,
  bounded timeouts, bounded response size, redaction, and indirect credential
  references.
- Observe at least three read-only source classes and two independent providers
  before allowing `p169_live_attachment_observed`.
- Record one immutable P169-owned receipt per network read and link receipts in
  an append-only hash chain.
- Retain only endpoint fingerprints, provider kind, timings, normalized hashes,
  redaction receipts, source time, collection time, and metadata.
- Verify raw responses, secrets, write requests, action execution, shell
  execution, staging mutation, production mutation, and external-model command
  counters are exactly zero.
- When no live endpoint is supplied, produce readiness evidence only and forbid
  `p169_live_attachment_observed`.
