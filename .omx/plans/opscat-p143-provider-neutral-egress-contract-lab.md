# OpsCat P143 — Provider-Neutral Egress Contract Lab

## Decision

P143 proves the contract required by a future external notification provider
without granting external notification authority. It consumes qualified P141
notification envelopes and qualified P142 loopback receipts, builds deterministic
provider-neutral egress intents, projects those intents into local shadow channel
profiles, evaluates compatibility, and persists replayable local evidence.

P143 does not deliver anything externally.

## Outcome

The milestone is complete only when all of the following are true:

1. An exact, immutable 52-case catalog passes with no skipped or reordered case.
2. All P143 source, tests, profiles, P141/P142 dependencies, matrix, review, and
   freeze artifacts are hash-bound into final release evidence.
3. Every forbidden authority counter is an exact integer zero.
4. Every allowed local counter reconciles to durable local artifacts.
5. Injected crash windows replay byte-identically or fail closed without network,
   provider, credential, shell, acknowledgement, action, or mutation authority.
6. Independent plan and implementation reviewers report P0/P1/P2/P3 = 0.
7. Focused, release, full, documentation, packaging, and security gates pass.

## Authority Boundary

### Allowed reads

- Qualified P141 release evidence and notification envelopes through existing
  public readers.
- Qualified P142 release evidence, dispatch records, journals, and receipts
  through new read-only P143 readers.
- Explicit local JSON shadow profiles inside validated immutable read roots.

### Allowed writes

- `p143.egress_contract_manifest.v1`
- `p143.shadow_provider_profile.v1`
- `p143.egress_intent.v1`
- `p143.provider_projection.v1`
- `p143.capability_result.v1`
- `p143.replay_journal.v1`
- `p143.egress_cursor.v1`
- `p143.egress_run.v1`
- qualification matrix, freeze manifest, reviews, and release evidence

### Forbidden authority

P143 must not read or derive credentials, authentication material, environment
configuration, URLs, endpoints, hostnames, headers, tokens, certificates, or
provider secrets. It must not use DNS, proxy configuration, TLS, HTTP clients,
provider SDKs, subprocesses, shells, external sockets, callbacks, P133
acknowledgements, approvals, actions, remediation, tickets, staging mutation,
production mutation, or operator replacement.

P143-owned config, CLI commands/options, public API parameters, runtime inputs,
shadow profiles, and generated P143 artifacts must not expose a `send`,
`deliver`, `endpoint`, `url`, `webhook`, `token`, `secret`, `header`, or `auth`
command or field. This lexical restriction does not prohibit read-only parsing
of an exact, allowlisted dependency field required to reject unsafe upstream
state. In particular, P143 must read P142 receipt `production_delivered` only to
prove that it is the literal boolean `false`; it must never copy that field into
a P143-owned config, API, command, or artifact.

### Exact forbidden counters

The complete P143 forbidden keyset is literal and immutable:

- `credential_read_count`
- `environment_read_count`
- `dns_socket_call_count`
- `proxy_use_count`
- `tls_handshake_count`
- `authentication_attempt_count`
- `redirect_follow_count`
- `provider_sdk_call_count`
- `non_loopback_socket_attempt_count`
- `external_message_send_count`
- `ticket_creation_count`
- `p133_ack_write_count`
- `approval_count`
- `subprocess_shell_count`
- `arbitrary_command_execution_count`
- `action_execution_count`
- `remediation_execution_count`
- `staging_mutation_count`
- `production_mutation_count`
- `operator_replacement_count`
- `authority_escape_count`
- `loopback_socket_attempt_count`
- `loopback_request_commit_count`
- `loopback_request_byte_count`
- `loopback_complete_response_count`
- `loopback_response_byte_count`
- `loopback_retry_count`
- `loopback_transport_failure_count`
- `loopback_http_2xx_count`
- `loopback_http_3xx_count`
- `loopback_http_4xx_count`
- `loopback_http_5xx_count`
- `provider_delivery_attempt_count`
- `provider_auth_material_count`
- `provider_endpoint_parse_count`
- `provider_callback_count`
- `external_http_request_count`
- `external_dns_resolution_count`

All 38 forbidden counters must exist, be `int` rather than `bool`, and equal
zero for P143 execution. Nonzero historical P142 loopback activity may be read
only from the qualified P142 dependency evidence and is never merged into P143
runtime counters.

### Exact allowed counters

- `intent_projection_count`
- `shadow_provider_validation_count`
- `capability_manifest_write_count`
- `replay_journal_entry_count`
- `compatibility_failure_count`
- `schema_rejection_count`

## Architecture

```text
P133 event
  -> P141 notification envelope
  -> P142 numeric-loopback receipt
  -> P143 provider-neutral egress intent
  -> deterministic local channel projection
  -> shadow capability evaluation
  -> durable local result + cursor + run evidence
```

### Components

1. `EgressContractConfig`
   - Closed schema and exact field set.
   - Explicit canonical absolute paths only.
   - Immutable read roots and disjoint writable roots.
   - Int-only budgets with bounded maxima.
2. `EgressIntentBuilder`
   - Binds P141 envelope hash, P142 receipt hash, destination, transition,
     severity, evidence references, deterministic intent ID, idempotency key,
     and dedupe key.
   - Never embeds raw log bodies, secrets, credentials, URLs, or endpoints.
3. `ShadowProviderProfile`
   - Provider-neutral channel types: `chat_message`, `email_message`,
     `pager_event`, `incident_comment`.
   - Describes only local capability limits and required fields.
4. `ProviderProjectionEngine`
   - Produces canonical JSON projections with deterministic truncation evidence.
   - No SDK imports or external transport.
5. `CapabilityEvaluator`
   - Evaluates required fields, channel support, payload/evidence limits,
     severity mapping, idempotency, dedupe, local retry classification, and
     manifest-only rate-limit semantics.
6. `ReplayJournal`
   - Durable intent, projection, result, and cursor phases.
   - Every terminal result has a persisted intent before artifact publication.
   - Existing artifacts must match exact canonical bytes or fail closed.
7. `ReleaseEvidenceBuilder`
   - Source-bound preliminary freeze followed by independent final review.

### Qualified P142 dependency contract

Before building an intent, P143 must validate all of the following as one
immutable dependency graph:

- P142 release status equals `p142_loopback_transport_lab_qualified` and its
  evidence hash equals
  `sha256:1d9f00eb142739a5da04fd0de3ebd19dc62a20ec94252d7a4d4f6b14ed02c254`.
- P142 freeze, matrix, final-review, config/profile, and P141 dependency hashes
  equal the values bound by that exact release evidence.
- The P142 dispatch record is canonical and binds the expected P141 envelope,
  destination ID, dispatch ID, attempt ID, payload hash, and config hash.
- The append-only P142 journal follows the legal phase graph without gaps,
  forks, duplicate ordinals, or conflicting prepared bytes.
- The terminal receipt binds the dispatch, journal, attempt ID, request/response
  hashes, P141 envelope, and `production_delivered is False`.
- The P141 envelope and P133 evidence references are canonical, hash-valid,
  immutable, and equal the bindings carried through P142.

Receipt hash validation alone is insufficient. Any mismatch in the graph fails
closed before a P143 intent or journal entry is written.

## Planned Files

- `app/services/p143_egress_contract_lab.py`
- `app/services/p143_runner.py`
- `app/services/p143_release_evidence.py`
- `app/p143_egress_contract_cli.py`
- `scripts/run_p143_egress_contract_lab.py`
- `tests/fixtures/p143/__init__.py`
- `tests/fixtures/p143/builders.py`
- `tests/test_p143_egress_contract_lab.py`
- `tests/test_p143_egress_contract_cli.py`
- `tests/test_p143_runner.py`
- `tests/test_p143_release_evidence.py`
- `evals/p143/input/egress-contract-lab-profile.json`
- `evals/p143/output/canonical-matrix.json`
- `evals/p143/output/freeze-manifest.json`
- `evals/p143/output/release-evidence.json`
- `evals/p143/final-implementation-review.json`
- `docs/operations/p143-test-spec.md`
- `docs/operations/p143-plan-review.md`
- `docs/operations/p143-implementation-review.md`

## Public API

```python
load_egress_contract_config(path) -> EgressContractConfig
validate_egress_contract_config(config) -> dict
process_egress_contracts(config, *, monotonic=None, wall_clock=None) -> dict
list_egress_results(config) -> list[dict]
build_egress_intent(config, envelope, loopback_receipt) -> dict
project_shadow_provider(intent, profile) -> dict
evaluate_shadow_capability(projection, profile) -> dict
```

## CLI Contract

```text
opscat-egress-contract-lab validate --config PATH
opscat-egress-contract-lab process --config PATH
opscat-egress-contract-lab list --config PATH
opscat-egress-contract-lab run --config PATH --max-cycles N
```

No delivery verb or authority-bearing option is permitted.

## Replay State Machine

Each intent uses a deterministic ID and an append-only journal:

```text
validated_source
  -> intent_prepared
  -> intent_written
  -> projection_prepared
  -> projection_written
  -> capability_result_prepared
  -> capability_result_written
  -> run_prepared
  -> cursor_written
  -> run_written
```

Rules:

- A prepared artifact contains its exact canonical object and byte hash.
- Recovery may publish only the prepared artifact bound to the journal.
- A result cannot exist without a valid projection and intent.
- Cursor advancement requires every profile result for one source event.
- Cursor advancement additionally requires a `run_prepared` journal entry that
  contains the exact canonical run object and byte hash.
- A crash after cursor durability but before run publication is recovered by
  publishing only the exact journal-bound prepared run bytes, without rereading
  providers or opening any I/O authority. A conflicting or missing prepared run
  fails closed; the cursor is never rolled back or advanced again.
- Same-sequence multi-profile work is one cursor batch.
- Conflicting, missing, reordered, skipped, symlinked, hardlinked, or
  noncanonical artifacts fail closed.

## Implementation Tickets

1. **P143-A — Plan/test contract**: freeze this plan, test spec, and critique.
2. **P143-B — Closed config**: schema, paths, ownership, budgets, profiles.
3. **P143-C — Dependency readers**: P141/P142 release and artifact validation.
4. **P143-D — Intent identity**: canonical intent, idempotency, dedupe, evidence refs.
5. **P143-E — Shadow projections**: four neutral channels and truncation evidence.
6. **P143-F — Capability evaluator**: closed severity and compatibility rules.
7. **P143-G — Durable replay**: journal, intents, projections, results, cursor, lease.
8. **P143-H — CLI and runtime**: bounded local cycles and exact counters.
9. **P143-I — Matrix/evidence**: exact catalog, anti-forgery, freeze, final review.
10. **P143-J — Release verification**: focused, release, P122, full, docs, secret scan.

## TDD Order

1. Config/schema/forbidden field tests.
2. Path ownership, link, overlap, and budget tests.
3. P141/P142 dependency, binding, and immutability tests.
4. Intent identity, idempotency, dedupe, severity, evidence-ref tests.
5. Four projection profiles and truncation tests.
6. Compatibility failure and manifest-only semantics tests.
7. Crash, replay, cursor batch, lease, tamper, and artifact-budget tests.
8. Patched forbidden entrypoint and exact counter tests.
9. CLI, runner anti-forgery, release evidence, and review binding tests.
10. Implementation only after the relevant failing tests exist.

## Release Gates

- Focused P143 tests, Ruff, and Mypy.
- Exact 52-case preliminary matrix.
- Independent implementation review with P0/P1/P2/P3 all zero.
- `bash scripts/verify.sh --profile p143-release`.
- `bash scripts/verify.sh --profile p122-release` after package changes.
- `bash scripts/verify.sh --profile full`.
- `bash scripts/verify.sh --profile docs`.
- Staged secret/path scan and `git diff --cached --check`.
- Private repository confirmation, Lore commit, push, and local/remote hash match.

## Frozen Release-Evidence Contract

`P143_SOURCE_PATHS` is the following exact tuple; no globbing or directory walk
is allowed:

```text
.omx/plans/opscat-p143-provider-neutral-egress-contract-lab.md
app/p143_egress_contract_cli.py
app/services/p143_egress_contract_lab.py
app/services/p143_release_evidence.py
app/services/p143_runner.py
docs/operations/p143-implementation-review.md
docs/operations/p143-plan-review.md
docs/operations/p143-test-spec.md
evals/p143/input/egress-contract-lab-profile.json
scripts/run_p143_egress_contract_lab.py
tests/fixtures/p143/__init__.py
tests/fixtures/p143/builders.py
tests/test_p143_egress_contract_cli.py
tests/test_p143_egress_contract_lab.py
tests/test_p143_release_evidence.py
tests/test_p143_runner.py
```

The release module must expose and enforce:

- `EXPECTED_PLAN_SHA256`: the reviewed plan hash recorded by the approved
  `p143-plan-review.md`.
- `EXPECTED_TEST_SPEC_SHA256`: the reviewed test-spec hash recorded by the same
  review artifact.
- `EXPECTED_P141_STATUS = "p141_notification_authority_simulator_qualified"`.
- `EXPECTED_P141_EVIDENCE_HASH =
  "sha256:d3028cf9f15c4f3936084182924eee8e1241f88ac67669502bcf36eac9ece788"`.
- `EXPECTED_P142_STATUS = "p142_loopback_transport_lab_qualified"`.
- `EXPECTED_P142_EVIDENCE_HASH =
  "sha256:1d9f00eb142739a5da04fd0de3ebd19dc62a20ec94252d7a4d4f6b14ed02c254"`.
- Exact plan-review binding, final implementation-review schema, reviewer agent
  identity, P0/P1/P2/P3 zero verdict, and source-bound preliminary freeze.

The exact required limitation keyset is:

- `provider_neutral_local_projection_lab_only_no_external_delivery`
- `no_credentials_auth_endpoints_urls_dns_proxy_tls_http_provider_sdk_or_environment_config`
- `no_p133_ack_approval_action_remediation_ticket_staging_production_mutation_or_operator_replacement`
- `p142_dependency_validation_does_not_grant_loopback_socket_authority_to_p143`
- `local_execution_provenance_not_cryptographic_attestation`
- `independent_reviewer_identity_not_externally_authenticated`
- `shadow_capability_compatibility_is_not_provider_certification`

The final review JSON is intentionally outside `P143_SOURCE_PATHS` to avoid a
self-hash cycle, but its canonical hash is bound by final release evidence.

## Non-Goals

- No real Slack, email, SMS, PagerDuty, webhook, ticket, or chat delivery.
- No provider certification claim.
- No endpoint validation or parsing.
- No credentials, auth lifecycle, TLS, DNS, proxy, rate-limit calls, callback,
  retry wait, or provider error handling.
- No acknowledgement or remediation authority.

## Stop Condition

Stop P143 and open a separate authority-expansion milestone if any requirement
needs credentials, an endpoint, external network, provider SDK, TLS, DNS,
authentication, acknowledgement, action, or mutation. P143 itself must remain a
pure local contract and compatibility lab.
