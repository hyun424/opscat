# P169 Plan Review

Decision: approved for governed read-only staging attachment only.

- Reuse the P153 live path and audited staging transport rules instead of
  creating a parallel connector authority.
- Enforce GET-only, exact host/path allowlists, HTTPS, bounded timeouts,
  response-size limits, redirect rejection, redaction, and indirect credential
  references.
- Persist endpoint fingerprints, provider kind, timings, normalized evidence
  hashes, redaction receipts, and P169-owned per-read hash-chain receipts only.
- Separate `p169_live_attachment_ready` from `p169_live_attachment_observed`;
  recorded transport can prove readiness, but observed status requires owner
  approval, live acknowledgement, scoped credential reference, and real network
  reads.
- Keep raw responses, secrets, writes, action execution, shell execution,
  staging mutation, and production mutation out of scope with exact-zero
  counters.
