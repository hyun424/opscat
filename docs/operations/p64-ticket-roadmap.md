# OpsCat P64 Ticket Roadmap — Audited Staging Credential + Transport Gate

P64 adds an audited credential and transport gate between P63 preflight eligibility and any network-capable staging GET transport. It does not read `.env`, does not require real credentials, and uses a mock secret store plus mock transport in verification.

## Tickets

- P64-001 — Gate fixture: define staging read-only credential refs, allowlisted hosts, approval IDs, audit sink, and unsafe blocked requests.
- P64-002 — Credential resolver: resolve only indirect `env:`/`secret:` refs from an injected mock secret store and reject raw token values.
- P64-003 — Approval gate: require explicit manual approval ID and bind it to every attempted request.
- P64-004 — Transport gate: allow only HTTPS GET requests to allowlisted staging hosts with safe timeout and P63/P62-ready connector status.
- P64-005 — Audit ledger: record decision, reasons, connector ID, host, method, approval ID, credential ref fingerprint, and redaction status for every request.
- P64-006 — Secret redaction: ensure raw credentials and authorization headers never appear in payloads, markdown, docs, or audit output.
- P64-007 — CLI smoke: emit JSON and Markdown in default dry-run mode with zero transport calls.
- P64-008 — Release evidence: wire docs, verification, full-profile evidence, and safety counters.

## Acceptance criteria

- Dry-run mode records audit decisions but makes zero transport calls.
- Mock live mode attempts only approved HTTPS GET requests for P63/P62-ready staging connectors.
- Missing approval, raw credential values, non-GET methods, disallowed hosts, production connectors, and unsafe timeouts are blocked.
- Every request has an audit ledger entry.
- Reports expose exact safety counters with no raw secret leakage.
