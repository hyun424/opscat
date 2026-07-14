# P140 P139-to-P133 Local Dead-Man Adapter

P140 connects the qualified P139 service host to the qualified P133 local
dead-man outbox without adding a delivery channel or action authority. It
revalidates P139 health and terminal receipts at check time, maps them through a
closed watchdog contract, and delegates all event, cursor, acknowledgement,
deduplication, reminder, recovery, and retention behavior to P133.

The implementation source of truth is
`.omx/plans/opscat-p140-p139-deadman-adapter.md`.

## Boundary

- credential-free and network-free;
- explicit local paths only;
- P140 -> P133 lease order, with P139 lease probed read-only;
- exact P133 event schema and exact-zero shared authority;
- no notification delivery, command execution, or remediation.

## Deployment preflight

P139's qualified status probe opens its service lease as `r+` before attempting
the nonblocking lock. Before Compose startup, create
`./data/p139/service.lock` as a regular file owned by `65532:65532` with mode
`0600`; otherwise a missing bind source may become a directory and validation
fails closed. The Compose template exposes only that exact file as writable
over the otherwise read-only P139 tree. The systemd template likewise grants
write-open access only to `/var/lib/opscat/p139/service.lock`. The configured
P139 bundle must use that same lease path.

## Tickets

1. closed config and secure loader;
2. P139 watchdog mapping and provenance;
3. adapter lease/check/run/signal lifecycle;
4. CLI and hardened deployment examples;
5. transition/tamper/crash/retention/subprocess tests;
6. exact 32-case frozen qualification;
7. independent review, docs, and verification integration;
8. final full verification and private-main release.

## Follow-on

P141 may separately review outbound notification-only authority. It must not
inherit action, remediation, credential-discovery, or production mutation
authority from P140.
