# P169 Tickets

Dependency: canonical P168 release. Owner surface: P153 staging-shadow live
path, audited staging transport reuse, P169 attachment service/runner/tests, and
P169 documentation only until implementation begins.

1. **P169-001 — Attachment contract.** Define the owner approval, live
   acknowledgement, indirect scoped credential reference, provider kind,
   endpoint fingerprint, source class, observed time, collection time, content
   hash, and redaction metadata required for every retained evidence item.
2. **P169-002 — Transport gates.** Enforce GET-only, exact host/path allowlists,
   HTTPS, bounded timeout, response-size limits, redirect rejection,
   production-label rejection, no raw credential persistence, and fail-closed
   handling for unsupported sources.
3. **P169-003 — Per-read receipts.** Emit a P169-owned immutable receipt for
   every network read and link receipts through an append-only hash chain. Do
   not treat P153 aggregate counters as equivalent evidence.
4. **P169-004 — Readiness vs observed evidence.** Produce
   `p169_live_attachment_ready` for recorded transport only. Produce
   `p169_live_attachment_observed` only after target-owner approval, live
   acknowledgement, indirect scoped credential reference, at least three source
   classes, two independent providers, and `real_network_call_count > 0`.
5. **P169-005 — Safety evidence.** Done when raw responses, secrets, writes,
   action execution, shell execution, staging mutation, production mutation, and
   external-model command counters are exactly zero.
