# OpsCat P96 Plan Review

## Decision

Proceed with a Prometheus read-only shadow connector as the first real telemetry integration.

## Review findings

- Reuse the existing typed connector registry, policy-aware service, redaction, audit, and incident evidence models.
- Keep network access out of normal tests and verification; fake transports prove the HTTP contract deterministically.
- Do not accept arbitrary per-request base URLs. The endpoint must come from trusted process configuration so alert or user payloads cannot redirect the agent to internal services.
- Permit plaintext HTTP only for loopback development endpoints. Require HTTPS for non-loopback allowlisted hosts.
- Bound query length, series count, response bytes, timeout, range duration, and estimated sample points.
- Store normalized metric observations rather than raw provider payloads.
- Do not connect the LLM or action executor directly in P96. P97 will consume this evidence through the investigation loop after P96 proves safe collection.

## Acceptance gate

P96 is complete only when fixture mode makes zero network calls, real mode cannot reach non-allowlisted destinations, successful results become scoped incident evidence, provider errors fail closed without leaking tokens, and the full repository verification remains green.

