# P142 Loopback Notification Transport Lab

## Outcome

Introduce a separately reviewed, credential-free, loopback-only HTTP transport
lab that consumes qualified P141 notification envelopes and writes durable
transport receipts. P142 is a lab milestone only: it may open actual local
sockets only to numeric loopback addresses and it must not claim production
notification delivery.

## Scope

- Consume P141 envelopes and P141 release evidence only through explicit local
  paths.
- Dispatch HTTP requests only to configured numeric loopback authorities:
  canonical dotted-quad `127.0.0.0/8` IPv4 literals except `127.0.0.0` and
  `127.255.255.255`, or the exact bracketed IPv6 literal `[::1]`, with an
  explicit decimal port in `1..65535` and a bounded, already-normalized
  origin-form path.
- Use plain HTTP only. TLS, credentials, authentication, redirects, proxies,
  DNS, hostname resolution, environment-derived settings, and provider SDKs are
  forbidden.
- Persist deterministic dispatch records and durable loopback transport
  receipts with idempotent replay and crash recovery.
- Preserve exact-zero non-transport authority counters: credentials, DNS,
  proxy, TLS, auth, redirects, external messages, tickets, P133 ack, arbitrary
  command/subprocess, approval, action, remediation, staging mutation,
  production mutation, operator replacement, and authority escape.
- Produce a frozen source-bound qualification matrix, independent review, and
  private-main release evidence.

## Non-goals

- No production notification channel, real operator paging, email, SMS, Slack,
  webhook, cloud, SaaS, or provider integration.
- No credentials, secrets, bearer tokens, API keys, headers carrying auth, TLS
  trust configuration, or mTLS.
- No DNS, hostname allowlists, proxy support, redirect following, arbitrary
  commands, P133 acknowledgement, action execution, remediation, or mutation.
- No changes to P141 envelope generation or P133 ownership semantics.

## Authority Boundary

Allowed:

- Read P141 envelope, receipt, cursor, and release-evidence artifacts through
  explicit paths.
- Bind to P141 envelope hashes, P141 config hashes, and the qualified P141 final
  evidence hash.
- Open outbound HTTP client sockets only to numeric loopback addresses that
  remain loopback after structural parsing.
- Write P142-owned dispatch, transport receipt, cursor, lease, run, matrix,
  manifest, review, and release-evidence artifacts under explicit local roots.

Forbidden:

- DNS resolution or hostname input of any kind, including `localhost`.
- Non-loopback IPs; every IPv4-mapped IPv6 literal including mapped loopback;
  alternate decimal, octal, hexadecimal, integer, abbreviated, or mixed IPv4
  syntax; IPv6 zone IDs; bracketless IPv6; and link-local, private LAN, public,
  wildcard, multicast, broadcast, or unspecified addresses.
- The two explicitly reserved IPv4 literals `127.0.0.0` and
  `127.255.255.255`, even though they are within `127.0.0.0/8`; IPv6 other than
  exact `[::1]`.
- Userinfo, query, or fragment components; missing, zero, signed, non-decimal,
  or out-of-range ports; and any path whose raw form is not its one permitted
  canonical form.
- Proxy environment variables or proxy configuration; environment reads must be
  patched to fail in valid paths.
- Redirect following, TLS, auth, credentials, cookies, custom secret-bearing
  headers, provider SDKs, external message authority, ticket creation, P133 ack,
  actions, remediation, staging mutation, production mutation, and arbitrary
  shell/subprocess execution.

## Dispatch Identity and Idempotency

Every base dispatch is derived deterministically from:

- P142 transport config hash;
- P141 envelope hash and envelope ID;
- P141 source event hash;
- destination ID;
- loopback route ID;
- HTTP method, numeric loopback authority, normalized path, and canonical body
  hash.

The base dispatch ID is `stable_hash(config_hash, envelope_hash,
destination_id, route_id, method, authority, path, body_hash)` and explicitly
excludes the attempt ordinal. The attempt ID is
`stable_hash(dispatch_id, attempt_ordinal)` and therefore includes the bounded,
zero-based attempt ordinal. Every retry carries the unchanged base dispatch ID
as the lab sink's idempotency key while retaining its distinct attempt ID.
Existing dispatch, journal, and receipt artifacts are reused only when their
canonical bytes and hashes match the deterministic expectation. Any
contradictory replay fails closed before another socket is opened.

## Retry, Backoff, and Time Budgets

- Configuration defines `max_attempts`, `connect_timeout_ms`,
  `response_timeout_ms`, `body_read_timeout_ms`, `max_response_bytes`,
  `max_total_dispatch_ms`, `base_backoff_ms`, `max_backoff_ms`, and
  `max_retry_after_ms`.
- Retries are allowed only when an attempt records a connection failure while
  its durable phase is still `pre_socket`. That attempt is never reopened; the
  scheduler may append only the next contiguous ordinal, subject to attempt,
  backoff, and remaining monotonic time budgets. Any
  `request_committed` attempt, with or without a complete response, can never
  create a next attempt or socket. HTTP `408`, `425`, `429`, and `5xx` are
  recorded as terminal complete responses rather than retried.
- `Retry-After` delta-seconds accepts only unsigned base-10 integers. Its date
  form accepts only strict IMF-fixdate with literal `GMT`, parsed against an
  injected timezone-aware UTC wall clock. The date delay is
  `max(0, ceil(server_date_utc - injected_wall_clock_utc))` whole seconds;
  stale dates produce zero and no wait.
- P142 records a valid bounded `Retry-After` delay as advisory response evidence
  but performs no post-commit sleep or retry. Obsolete RFC 850/asctime forms,
  malformed or ambiguous dates, non-UTC offsets/tokens, negative delta-seconds,
  and values exceeding `max_retry_after_ms` or the remaining monotonic dispatch
  budget are rejected and recorded. Wall-clock parsing never changes or extends
  the monotonic deadline.
- Backoff is deterministic with no random jitter. The receipt records the
  computed schedule; tests use an injected monotonic clock and sleep recorder.

## Crash Recovery and Durability

- Single-writer execution uses a nonblocking P142 lease.
- Every base dispatch has a durable `p142.dispatch_attempt_journal.v1`. Every
  journal entry requires `attempt_ordinal` and the deterministic `attempt_id`,
  and monotonically growing entries use only these phases:
  `pre_socket`, `request_committed`, `complete_response_observed`, and
  `receipt_written`. Ordinals start at zero, are contiguous, never reused, and
  every entry's attempt ID must equal
  `stable_hash(dispatch_id, attempt_ordinal)`.
- The exact per-attempt transition graph is the linear prefix `pre_socket` ->
  `request_committed` -> `complete_response_observed` -> `receipt_written`; no
  phase can be skipped, repeated, or reversed. A `pre_socket` entry with a
  durably recorded connection failure may terminate that attempt without a
  phase transition and authorize one next-ordinal `pre_socket` entry. A
  terminal prefix remains at its last durable phase; it must not fabricate a
  later phase.
- Each transition is canonicalized and committed with temp-file, file-fsync,
  atomic-replace, and directory-fsync discipline before the next side effect.
- `pre_socket` is durable before opening a socket. After a successful connect,
  `request_committed` is durably recorded immediately before the first request
  byte may be written. It is a conservative no-replay barrier: it means the
  request may have reached the sink, even if a crash occurs before any byte is
  actually written.
- `complete_response_observed` is durable only after the complete bounded
  status, relevant headers, body hash/truncation evidence, and timing evidence
  needed to reconstruct policy and receipt output are recorded.
- `receipt_written` is durable only after the terminal transport receipt exists,
  file-fsyncs, atomically replaces its target, directory-fsyncs, and its hash is
  recorded in the journal.
- Replay from `pre_socket` may append the next ordinal only when that exact
  entry already contains a hash-valid durable connection-failure record. An
  incomplete or outcome-free `pre_socket` recovery state opens zero sockets,
  creates no next ordinal, and fails closed. Replay whose latest phase is
  `request_committed` without a later
  `complete_response_observed` opens zero sockets, performs zero retries, and
  writes a terminal receipt with
  `failure_class="request_committed_response_unknown"`,
  `delivered_to_loopback=false`, `production_delivered=false`, and
  `acknowledged=false`. Its journal remains at the `request_committed` terminal
  prefix because no complete response was observed; the receipt is validated
  separately and no next ordinal is permitted. Replay from
  `complete_response_observed` reconstructs and writes the terminal receipt
  without reopening the attempt or creating a next ordinal. Replay from
  `receipt_written` validates and reuses the receipt with zero sockets.
- Dispatch journals and receipts use the same temp-file, file-fsync,
  atomic-replace, and directory-fsync discipline.
- Cursor advancement occurs only after every required receipt for an envelope is
  durable.
- Crash tests cover every durable phase, the socket-open-to-no-replay-barrier
  interval, response-before-phase persistence, receipt-before-cursor,
  multi-destination partial completion, and contradictory local artifacts.
- P142 never prunes or mutates P141/P133 semantic artifacts. The only permitted
  changes under those trees are synchronization metadata at the exact lease
  paths used by the P141 and P133 public-reader APIs; those APIs own the writes,
  and all event, envelope, simulated receipt, cursor, acknowledgement, and
  release-evidence bytes remain unchanged.

## Path, FD, and SSRF Hardening

- Config distinguishes P141/P133 read roots from P142 writable roots. They are
  absolute or resolved from the config file, must stay under their declared
  roots, and must be pairwise non-overlapping. Dependency read roots are never
  treated as P142 output roots; exact public-reader lease paths remain separate
  dependency synchronization paths.
- Every P142 writable root and writable directory below it must satisfy
  `st_uid == os.geteuid()`, have owner write and owner search bits set, and have
  both group-write and world-write bits clear. Reject roots that fail effective
  UID ownership or mode checks before creating a lease, journal, receipt,
  cursor, run, matrix, manifest, review, or release artifact.
- Reject traversal, symlink components, hardlinks, nonregular files, unsafe
  permissions on writable roots, overlapping P141/P142 ownership, and file
  replacement drift between validation and read/write.
- Re-open artifacts through validated parent directory descriptors where
  deletion or overwrite risk exists.
- Parse authority components before any socket call. IPv4 must be exactly four
  canonical base-10 octets with no leading zeros, first octet `127`, and must
  not equal `127.0.0.0` or `127.255.255.255`; IPv6 must be exactly `[::1]`.
  Then confirm loopback semantics and obtain packed bytes with `ipaddress`.
  Reject IPv4-mapped IPv6 including `[::ffff:127.0.0.1]`, alternate
  decimal/octal/hex/integer/mixed IPv4, zone IDs, bracketless IPv6, userinfo,
  query, fragment, and invalid ports before socket construction.
- Permit only `/` or an already-normalized ASCII origin-form path whose segments
  contain `[A-Za-z0-9._~-]+`. Reject repeated slashes, `.`/`..` segments,
  percent escapes or encoded delimiters, backslashes, controls, whitespace,
  query/fragment delimiters, and any parse/render mismatch rather than
  normalizing ambiguous input.
- Disable automatic redirect behavior and reject any `Location` header evidence
  as non-followed.
- Construct a raw `socket.socket(socket.AF_INET, socket.SOCK_STREAM)` for an
  accepted IPv4 target or `socket.socket(socket.AF_INET6, socket.SOCK_STREAM)`
  for `[::1]`. Connect only to the canonical numeric text produced by
  `socket.inet_ntop(family, parsed_address.packed)` and the validated port,
  using `(address, port)` for IPv4 and `(address, port, 0, 0)` for IPv6.
- Forbid `http.client.HTTPConnection.connect`, `socket.create_connection`, and
  `socket.getaddrinfo` in all P142 runtime paths; tests patch each to fail. If
  `http.client.HTTPResponse` is used for parsing, it receives only the already
  connected raw socket and must not own or initiate connection establishment.

## Closed Schemas

- `p142.loopback_transport_config.v1`
- `p142.dispatch_record.v1`
- `p142.dispatch_attempt_journal.v1`
- `p142.loopback_transport_receipt.v1`
- `p142.loopback_transport_cursor.v1`
- `p142.loopback_transport_run.v1`
- `p142.release_case_matrix.v1`
- `p142.freeze_manifest.v1`
- `p142.final_implementation_review.v1`
- `p142.release_evidence.v1`

Required receipt fields include schema, config hash, P141 envelope binding,
dispatch ID, attempt IDs, numeric loopback authority, method, path, request body
hash, status code or failure class, response body hash or truncation marker,
timing budget summary, retry schedule, delivered-to-loopback boolean,
production-delivered boolean fixed false, acknowledged boolean fixed false,
transport counters, exact-zero non-transport counters, and receipt hash.

## Exact Counter Contracts

The forbidden non-transport authority counter keyset is literally and exactly:

```text
credential_read_count
environment_read_count
dns_socket_call_count
proxy_use_count
tls_handshake_count
authentication_attempt_count
redirect_follow_count
provider_sdk_call_count
non_loopback_socket_attempt_count
external_message_send_count
ticket_creation_count
p133_ack_write_count
approval_count
subprocess_shell_count
arbitrary_command_execution_count
action_execution_count
remediation_execution_count
staging_mutation_count
production_mutation_count
operator_replacement_count
authority_escape_count
```

The allowed transport activity counter keyset is literally and exactly:

```text
loopback_socket_attempt_count
loopback_request_commit_count
loopback_request_byte_count
loopback_complete_response_count
loopback_response_byte_count
loopback_retry_count
loopback_transport_failure_count
loopback_http_2xx_count
loopback_http_3xx_count
loopback_http_4xx_count
loopback_http_5xx_count
```

Receipts, run output, matrices, and release evidence must contain both exact
keysets with no missing or unknown keys. Every value must satisfy
`type(value) is int`; booleans are invalid. Every forbidden value must equal
zero. Every transport value must be non-negative and consistent with journal,
socket, byte, retry, failure, and bounded response-status evidence.

## Exact Planned Files

Planning artifacts created in this planning pass:

- `.omx/plans/opscat-p142-loopback-notification-transport-lab.md`
- `docs/operations/p142-test-spec.md`

Implementation and release files planned for P142:

- `app/p142_loopback_cli.py`
- `app/services/p142_loopback_transport_lab.py`
- `app/services/p142_runner.py`
- `app/services/p142_release_evidence.py`
- `scripts/run_p142_loopback_transport_lab.py`
- `tests/fixtures/p142/__init__.py`
- `tests/fixtures/p142/builders.py`
- `tests/test_p142_loopback_transport_lab.py`
- `tests/test_p142_loopback_cli.py`
- `tests/test_p142_runner.py`
- `tests/test_p142_release_evidence.py`
- `evals/p142/input/loopback-transport-lab-profile.json`
- `evals/p142/output/canonical-matrix.json`
- `evals/p142/output/freeze-manifest.json`
- `evals/p142/output/release-evidence.json`
- `evals/p142/final-implementation-review.json`
- `docs/operations/p142-plan-review.md`
- `docs/operations/p142-test-spec.md`
- `docs/operations/p142-implementation-review.md`
- `pyproject.toml`
- `scripts/verify.sh`

No `deploy/p142` production manifest is planned for P142.
`docs/operations/p142-plan-review.md` is an exact planned, source-bound file but
is intentionally not created by this amendment; an independent reviewer must
produce it after reviewing the amended plan and before P142 implementation.

## Ticket Order

### P142-000 - Independent plan review

Create `docs/operations/p142-plan-review.md` with reviewer identity distinct
from the plan author, an explicit APPROVED verdict, resolved critic findings,
the exact hashes of this plan and test spec, and the lab-only evidence boundary.
No implementation ticket may start before this source-bound review passes.

### P142-001 - Contract and closed configuration

Define closed schemas, numeric-loopback-only route configuration, strict path
ownership, byte/count/free-space budgets, retry/time budgets, and exact counter
maps. Reject DNS, non-loopback, proxy, TLS, auth, credential, redirect,
command, P133 ack, action, remediation, mutation, noncanonical address/port, and
ambiguous path fields or values.

### P142-002 - P141 envelope binding

Read P141 artifacts without mutating them; validate P141 envelope hashes,
receipt bindings, cursor consistency, qualified P141 release evidence, and
source-event lineage before dispatch.

### P142-003 - Loopback HTTP client

Implement the minimal standard-library HTTP transport with numeric-loopback
socket enforcement, family-specific raw sockets connected from parsed packed
addresses, forbidden hostname-capable connection helpers, no redirects, no
proxies/env, no TLS/auth, bounded request/response bodies, and explicit
connect/response/body deadlines.

### P142-004 - Deterministic dispatch and durable receipts

Add deterministic dispatch IDs, attempt IDs, idempotent replay, receipt
canonicalization, the durable four-phase attempt journal, the
`request_committed` no-replay terminal rule, atomic writes, cursor advancement,
and conflict detection.

### P142-005 - Retry/backoff and Retry-After policy

Add bounded deterministic retries, safe `Retry-After` support, total dispatch
budget enforcement, pre-socket-failure-only ordinal advancement, strict
IMF-fixdate parsing, advisory delay recording, and injected monotonic plus UTC
wall-clock controls for tests.

### P142-006 - Crash recovery and filesystem hardening

Cover lease conflicts, crash windows, symlink/hardlink/path escape, unsafe
writable-root ownership/modes, read/write root separation, file replacement
drift, low space, and budget overflow. Prove P141 and P133 semantic artifacts
remain byte-immutable while allowing only the exact public-reader lease
synchronization metadata paths to change.

### P142-007 - Frozen test catalog and release runner

Implement the exact ordered 44-case catalog in `p142_runner`, anti-forgery
matrix validation, source-bound profile, and final mode that consumes frozen
inputs without rewriting them.

### P142-008 - Independent review

Produce an implementation review by an identity distinct from the implementer,
covering loopback-only SSRF defenses, durability, P141 binding, non-transport
authority counters, retry semantics, and release limitations.

### P142-009 - Verification and private-main release

Add `opscat-loopback-transport-lab`, `p142-release`, source-bound evidence, and
Lore-protocol commit/push to private `main` only after P141 dependency
reproduction, P142 targeted tests, lint, typecheck, docs checks, release
evidence validation, and independent review pass.

## Acceptance Criteria

1. Config accepts only closed P142 schemas with numeric loopback routes and
   rejects every DNS, non-loopback, proxy, TLS, auth, credential, redirect,
   command, P133 ack, action, remediation, mutation, noncanonical address/port,
   or ambiguous path surface enumerated in the test spec.
2. Valid dispatches consume only hash-valid P141 envelopes bound to the
   qualified P141 final evidence hash.
3. The transport opens only raw family-specific `AF_INET`/`AF_INET6` sockets and
   connects to canonical numeric text reconstructed from validated packed
   bytes. `HTTPConnection.connect`, `socket.create_connection`, and
   `socket.getaddrinfo` are never called; `HTTPResponse`, if used, receives only
   the preconnected socket.
4. Any hostname, DNS path, proxy/env read, TLS/auth attempt, redirect follow,
   non-loopback address, `127.0.0.0`, `127.255.255.255`, or credential-bearing
   field fails before dispatch. Other canonical `127/8` addresses and exact
   `[::1]` remain eligible.
5. Dispatch IDs exclude attempt ordinal; attempt IDs include it. Both IDs,
   request body bytes, journals, and receipt bytes are deterministic for the
   same config and P141 envelope.
6. Replay after successful dispatch is byte-identical and opens zero additional
   sockets.
7. Contradictory replay, tampered local artifacts, path escape, symlink, and
   hardlink checks fail closed. Every P142 writable root is effective-UID owned,
   owner writable/searchable, and neither group nor world writable; dependency
   read roots are separate.
8. Only a durable `pre_socket` connection failure may authorize the next
   contiguous ordinal. Strict delta-seconds/IMF-fixdate `Retry-After` evidence
   uses injected UTC wall time, whole-second ceiling, stale-date zero, and the
   remaining monotonic budget; it never creates a post-commit sleep or retry.
9. Every journal entry includes `attempt_ordinal` and `attempt_id`, and every
   attempt is a prefix of the exact phase graph `pre_socket` ->
   `request_committed` -> `complete_response_observed` -> `receipt_written`.
   Recovery from `request_committed` without a complete response opens zero
   sockets, creates no next ordinal, and emits exactly
   `failure_class="request_committed_response_unknown"`,
   `production_delivered=false`, and `acknowledged=false`; no cursor advances
   ahead of durable receipts.
10. Receipts, runs, matrices, and release evidence contain exactly the literal
    forbidden and transport counter keysets defined above. Values are integers,
    never booleans; forbidden counters are exactly zero and transport counters
    are non-negative and evidence-consistent.
11. P141 and P133 event, envelope, receipt, cursor, acknowledgement, and
    release-evidence artifacts are byte-identical before and after valid P142
    runs. Only synchronization metadata at the exact lease paths written by the
    P141/P133 public-reader APIs may differ.
12. The exact ordered 44-case catalog cannot skip, reorder, forge hashes, hide
    nonzero counters, use boolean counters, or rewrite frozen final inputs.
13. Final evidence binds the P142 plan, P142 test spec,
    `docs/operations/p142-plan-review.md`, source files, tests, profile,
    canonical matrix, freeze manifest, independent implementation review, and
    P141 final release evidence hash.
14. Release documentation states P142 is a loopback-only transport lab and does
    not prove production delivery, provider compatibility, credential handling,
    external alerting, or operator acknowledgement.

## Test Matrix

The frozen catalog has 44 ordered cases:

- 8 config and authority-surface cases;
- 7 P141 envelope-binding cases;
- 8 loopback HTTP transport cases;
- 8 retry/backoff and crash-recovery cases;
- 5 durability/resource cases;
- 4 non-transport authority and mutation cases;
- 4 release-evidence cases.

The exact selector catalog is defined in `docs/operations/p142-test-spec.md`
and must be copied verbatim into `app/services/p142_runner.py`.

## Verification Plan

- `uv run --no-sync --extra dev pytest -q tests/test_p142_loopback_transport_lab.py`
- `uv run --no-sync --extra dev pytest -q tests/test_p142_loopback_cli.py`
- `uv run --no-sync --extra dev pytest -q tests/test_p142_runner.py`
- `uv run --no-sync --extra dev pytest -q tests/test_p142_release_evidence.py`
- `uv run --no-sync --extra dev ruff check app tests scripts`
- `uv run --no-sync --extra dev mypy app tests scripts`
- `bash scripts/verify.sh --profile p142-release`

`p142-release` must run P141 release-profile reproduction first, then the P142
targeted tests, then final P142 evidence assembly against frozen tracked inputs.

## Stop Conditions

- Any ambiguity about whether a target is numeric loopback, or acceptance of
  `127.0.0.0`, `127.255.255.255`, or IPv6 other than exact `[::1]`.
- Any acceptance of IPv4-mapped IPv6, alternate decimal/octal/hex/integer/mixed
  IPv4, a zone ID, bracketless IPv6, userinfo/query/fragment, an invalid port,
  or a path requiring normalization.
- Any hostname, DNS lookup, environment/proxy read, non-loopback address, TLS,
  auth, credential, redirect follow, provider SDK, arbitrary command, or
  subprocess attempt in runtime code.
- Any use of `HTTPConnection.connect`, `socket.create_connection`, or
  `socket.getaddrinfo`; any socket family/address mismatch; any connect target
  not reconstructed from validated packed bytes; or any `HTTPResponse` parser
  given a socket it did not receive already connected.
- Any P141 envelope hash, config hash, cursor, receipt, or release-evidence
  binding drift.
- Any P133 ack, external-message, ticket, approval, action, remediation, staging
  mutation, production mutation, operator replacement, or authority escape
  counter that is nonzero or boolean.
- Any path outside declared roots, read/write root overlap, symlink, hardlink,
  nonregular file, P142 writable root not owned by effective UID, missing owner
  write/search permission, group/world-writable directory, or replacement drift.
- Any retry not caused by a durable `pre_socket` connection failure; any reused
  or skipped ordinal; any post-commit next attempt; or any `Retry-After` parser,
  rounding, wall-clock, sleep, or budget behavior outside the strict policy.
- Any missing/out-of-order attempt-journal transition; any replay of
  `request_committed` without a complete response that opens a socket, retries,
  creates a next ordinal, fabricates a later phase, or omits the exact terminal
  failure fields; any entry missing/mismatching ordinal or attempt ID; or any
  crash window that can advance a cursor before durable receipts.
- Any missing/unknown counter key, boolean counter value, nonzero forbidden
  counter, or transport counter inconsistent with journal/socket/byte evidence.
- Any frozen catalog skip, reorder, selector drift, output hash drift, forged
  source binding, stale final evidence, missing source-bound P142 plan review,
  or missing independent implementation review.

## Release Evidence Boundary

P142 release evidence may claim only that OpsCat can dispatch P141 envelopes to
an isolated numeric-loopback HTTP lab with deterministic, durable receipts and
strict authority counters. It must not claim production delivery, notification
SLOs, external provider compatibility, credential security, operator
acknowledgement, remediation, action execution, or production readiness.
