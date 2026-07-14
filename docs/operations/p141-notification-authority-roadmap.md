# P141 Notification-Only Authority Simulator

P141 turns validated P133 dead-man events into deterministic, redacted local
notification envelopes and simulated delivery receipts. It establishes the
shape and safety boundary of a future outbound notification channel while
performing no external delivery.

The implementation source of truth is
`.omx/plans/opscat-p141-notification-authority-simulator.md`.

## Boundary

- credential-free and network-free;
- explicit local paths and destination identifiers only;
- P133 remains event and acknowledgement owner;
- the exact P133 lease file may be written only by the public reader lock;
- simulated receipts always say not delivered and not acknowledged;
- exact-zero external-message, action, remediation, and mutation authority.

## Dependency order

P140 -> P133 events -> P141 local simulator. A later reviewed milestone may add
a real notification transport, but cannot inherit remediation or action
authority from P141.

## Tickets

1. closed contract and secure loader;
2. P133 binding and redacted envelope;
3. idempotent simulated receipts;
4. durable runner and CLI;
5. adversarial tests;
6. frozen qualification;
7. independent review;
8. full verification and private-main release.
