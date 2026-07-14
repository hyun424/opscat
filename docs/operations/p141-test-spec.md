# P141 Test Specification

## Contract tests

- Accept one closed, local configuration and reject unknown, secret-bearing,
  endpoint-bearing, overlapping, escaped, or symlinked configuration.
- Accept only configured local destination IDs and P133 transition kinds.
- Require exact schema fields, canonical hashes, exact-zero forbidden authority,
  and bounded UTF-8 artifact sizes.

## P133 binding tests

- Consume valid opened, updated, reminder, and recovered events in sequence.
- Reject malformed event schema, event-hash drift, config binding drift,
  sequence gaps, predecessor mismatch, rewind, fork, and conflicting replay.
- Prove that processing does not create, modify, or remove P133 event, cursor,
  or ack files. The public reader's exact lease file is synchronization metadata
  and is the only separately mounted writable P133 path.

## Envelope and receipt tests

- Produce deterministic IDs and bytes for identical input.
- Include only redacted minimal event projection and local evidence references.
- Persist `simulated=true`, `delivered=false`, `acknowledged=false`.
- Reject a receipt or envelope whose bytes, hash, attempt ID, or event binding
  differs from the deterministic expected value.

## Durability and resource tests

- Serialize processes with a nonblocking lease.
- Recover safely from envelope-only and envelope+receipt crash windows.
- Advance cursor only after durable envelope and receipt writes.
- Enforce artifact count, total bytes, per-artifact bytes, and free-space limits
  before writes; never prune P133-owned data.
- Stop cleanly on SIGINT/SIGTERM and reject clock rollback.

## Side-effect tests

- Patch socket, environment, subprocess, and P133 acknowledgement entry points
  to fail if called; all valid simulator paths must still pass.
- Assert exact-zero credential, network, external message, ticket, approval,
  action, remediation, production mutation, and authority escape counters.

## Release gate

- Exact ordered 36-case catalog: 6 config, 8 P133 binding, 8 envelope/receipt,
  6 durability/resource, 4 authority/non-mutation, and 4 release-evidence
  cases. Validators reject skip, reorder, selector drift, optimistic pass flags,
  forged activity/counters, output hash drift, and boolean counters.
- Independent plan and implementation review artifacts.
- Source-bound freeze manifest and final release evidence bound to qualified
  P133 and P140 evidence hashes.
- Ruff, Mypy, targeted tests, docs verification, and full verification pass.

## Required exact-zero counters

Credential reads, environment reads, DNS/socket/network calls, provider SDK
calls, external messages, ticket creation, P133 acknowledgements, approvals,
subprocess/shell, action execution, remediation, staging mutation, production
mutation, operator replacement, and authority escape.
