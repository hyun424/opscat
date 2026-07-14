# P142 Loopback Transport Roadmap

P142 adds a credential-free numeric-loopback-only HTTP transport lab after
P141. It consumes qualified P141 notification envelopes through explicit local
paths and writes deterministic P142 dispatch records, journals, receipts,
cursor state, matrix output, and release evidence.

This is not production delivery. P142 does not send email, SMS, Slack, webhook,
cloud, SaaS, provider, or operator notifications. It does not handle
credentials, TLS, auth, DNS, proxies, redirects, P133 acknowledgement, action
execution, remediation, staging mutation, production mutation, or operator
replacement.

The implementation contract is
`.omx/plans/opscat-p142-loopback-notification-transport-lab.md`. Independent
plan approval is recorded in `docs/operations/p142-plan-review.md`.

## Boundary

- credential-free, secret-free, auth-free, TLS-free, DNS-free, proxy-free;
- numeric loopback only: canonical `127/8` IPv4 except `127.0.0.0` and
  `127.255.255.255`, plus exact `[::1]`;
- hostnames, `localhost`, IPv4-mapped IPv6, alternate IPv4 syntaxes, zone IDs,
  userinfo, query, fragment, and path normalization are rejected;
- raw `AF_INET` or `AF_INET6` sockets are opened only after target validation;
- P141/P133 artifacts are read-only except exact public-reader lease metadata;
- P142-owned artifacts are written only under effective-UID-owned local roots;
- forbidden non-transport authority counters must be present and exactly zero;
- transport counters must be integer, bounded, and evidence-reconciled.

## Dependency Order

P140 -> P133 events -> P141 notification envelopes -> P142 local loopback lab.
A later separately reviewed milestone may add a real notification transport,
but cannot inherit production delivery, credential, acknowledgement, action, or
remediation authority from P142.

## Tickets

1. P142-000: independent plan review with explicit approval and source hashes;
2. P142-001: closed configuration, schemas, budgets, and counter maps;
3. P142-002: P141 envelope and release-evidence binding;
4. P142-003: numeric-loopback raw-socket HTTP client;
5. P142-004: deterministic dispatch IDs, journals, receipts, and cursor;
6. P142-005: bounded retry/backoff and strict advisory `Retry-After` handling;
7. P142-006: crash recovery, lease safety, and filesystem hardening;
8. P142-007: exact 44-case catalog, runner, and anti-forgery matrix;
9. P142-008: independent implementation review;
10. P142-009: verification profile, source-bound evidence, and private-main
    release.

## Release Boundary

P142 may claim only `loopback_transport_lab_qualified` after the exact 44-case
catalog passes, P141 dependency evidence reproduces, exact-zero authority
counters validate, P141/P133 immutability is proven, independent implementation
review passes, and `bash scripts/verify.sh --profile p142-release` succeeds.

The release must state that P142 proves deterministic dispatch to an isolated
numeric-loopback HTTP lab with durable receipts. It must not claim production
notification delivery, provider compatibility, credential handling, external
alerting, notification SLOs, P133 acknowledgement, remediation, action
execution, operator replacement, or production readiness.
