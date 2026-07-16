# P153 Staging Read-only Shadow Observation Plan

## Objective

P153 turns the qualified P152 bounded operator agent into a staging-attachable,
read-only observation runtime. It must be able to poll Prometheus, Loki, and
Sentry-shaped HTTP APIs, normalize evidence, request bounded follow-up
observations, and produce an evidence-grounded incident judgment without
executing an action.

## Release claim

The canonical release qualifies the staging shadow transport, normalization,
durable cursor, evidence investigation, abstention, and audit contracts through
an injected recorded transport. It does not claim that a user staging system was
attached because no user staging endpoints or credentials are available in the
repository.

The same runner exposes an explicit `live` mode. Live mode requires:

- a separate local profile containing only HTTPS staging endpoints;
- exact host allowlisting;
- GET-only provider routes;
- indirect environment-variable secret references;
- the explicit acknowledgement
  `OPSCAT_STAGING_SHADOW_ACK=read-only-staging`;
- bounded timeout, response, record, source, and investigation budgets.

## Safety invariants

1. Only Prometheus, Loki, and Sentry provider kinds are accepted.
2. Every provider operation is HTTP GET and path-allowlisted.
3. Production environments, write methods, redirects, request-controlled
   authorization headers, raw credentials, and unallowlisted hosts fail closed.
4. Credentials may be resolved from named environment variables in live mode,
   but values are never written to reports, state, logs, or receipts.
5. Canonical qualification performs zero real network calls and zero external
   model calls.
6. The runtime may produce observations, hypotheses, evidence requests,
   abstentions, and proposed responses. It cannot approve or execute actions.
7. Missing or contradictory evidence results in `insufficient_evidence`, not a
   fabricated diagnosis.
8. Durable state is atomically written and self-hashed. Forward writes preserve
   monotonic generation/cursors; malformed or hash-corrupt state fails closed.
   Detecting a validly re-signed rollback requires an external ledger and is
   deferred.
9. Release evidence binds current source files and the complete P152 companion
   artifact set.

## Architecture

```text
staging profile
  -> profile/authority validation
  -> read-only transport
  -> provider normalizers
  -> durable cursor + dedupe state
  -> anomaly evidence extraction
  -> bounded evidence-gap request generator
  -> hypothesis support/contradiction scoring
  -> incident-likely or insufficient-evidence judgment
  -> immutable audit and release evidence
```

## Provider contracts

- Prometheus: `/api/v1/query` or `/api/v1/query_range`.
- Loki: `/loki/api/v1/query` or `/loki/api/v1/query_range`.
- Sentry: `/api/0/.../issues/` and issue event read routes.

Every response is size-bounded before JSON parsing. Normalized records contain
provider, source, timestamp, service, signal kind, severity, summary, labels,
and a content hash. Selected summaries and label maps are recursively redacted;
raw provider payloads and authorization values are never persisted.

## Qualification gates

- Three provider sources and at least two independent supporting providers.
- At least one evidence-grounded likely-incident case.
- At least one correct abstention caused by missing evidence.
- Retry and rate-limit handling remains within the frozen budget.
- One persisted-state resume with no duplicate normalized evidence.
- Exact-zero real-network, model, action, production-mutation, write-request,
  and secret-persistence counters in canonical release evidence.
- P153-owned service coverage at least 80%.

## Follow-up

P154 consumes real P153 shadow session ledgers over 7-14 days and compares agent
judgments with operator-confirmed outcomes. P153 itself does not make a general
accuracy or production operator replacement claim.
