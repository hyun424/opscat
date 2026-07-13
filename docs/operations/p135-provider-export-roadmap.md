# P135 Provider-Shaped Export Attachment

## Outcome

P135 turns the policy-only P134 boundary into a bounded, credential-free local
observation path. It reads operator-supplied local files shaped like Prometheus,
Loki, Grafana, Sentry, and OpenTelemetry exports, normalizes selected evidence,
and emits source-bound execution receipts.

P135 does not call a provider, resolve a URL, read a credential, open a socket,
launch a process, deliver a notification, execute an action, mutate staging or
production, or claim operator replacement. P136 is the first phase that may
propose a separately reviewed opt-in GET-only live shadow.

## Authority composition

- Every file read requires a current `allowed` P134 decision receipt whose
  proposal has `requested_level=OA1_LOCAL_ARTIFACT`,
  `method=LOCAL_READ_FILE`, and the matching telemetry capability.
- `provider-shaped local export attachment` is a P135 release classification,
  not a promotable P134 OA2 authority level. P135 does not silently widen the
  P134 contract: `OA2_PROVIDER_SHAPED_LOCAL_EXPORT`, OA3, and OA4 remain denied
  by P134.
- A P134 estimate is an upper bound. The pre-read stat size must not exceed the
  approved byte estimate and the normalized record count must not exceed the
  approved record estimate.
- P135 increments local file-observation counters. Provider calls, sockets,
  credentials, subprocesses, delivery, action, and mutation counters remain
  exact integer zero.
- A P134 receipt proves policy allowance; a P135 execution receipt proves what
  bounded local bytes were actually read and normalized. Neither authenticates
  the operating-system user.

## Supported local export profiles

The closed provider set and first qualified shapes are:

1. `prometheus` / `prometheus.query_range.matrix.v1` - a successful Prometheus
   HTTP API matrix result with metric labels and `[timestamp, value]` samples.
2. `loki` / `loki.query_range.streams.v1` - a successful Loki range-query
   streams result with stream labels and nanosecond timestamp/log-line pairs.
3. `grafana` / `grafana.dashboard.classic.v1` - a Classic dashboard JSON model;
   panels and datasource/query declarations become topology metadata evidence,
   not observed metric values.
4. `sentry` / `sentry.issues.api.list.v1` - a bounded top-level array shaped
   like Sentry's issue-list API response; issue entries become event evidence.
5. `opentelemetry` / `otlp.file.jsonl.v1` - OpenTelemetry file-exporter JSONL
   whose entire artifact contains exactly one declared signal family:
   `resourceMetrics`, `resourceLogs`, or `resourceSpans`. A manifest may attach
   multiple OTLP artifacts, but no individual file may mix signal families.

Binary protobuf, gzip, archives, YAML, CSV, arbitrary JSON, Grafana database
files, Sentry envelopes, Prometheus exposition text, provider SDK responses not
matching the declared profile, and mixed-signal OTLP lines are not qualified in
P135. Additional shapes require a new reviewed adapter version and fixtures.

The adapter contracts follow current upstream documentation. Prometheus range
vectors use `resultType=matrix`; Loki range queries use `streams`; Grafana
Classic exports contain dashboard metadata and panels; OTLP JSON follows lower
camel-case protobuf JSON and encodes 64-bit integers as decimal strings. The
OpenTelemetry file-exporter specification is Development, so its adapter name
and qualification remain explicitly versioned.

Upstream shape references:

- Prometheus HTTP API: <https://prometheus.io/docs/prometheus/latest/querying/api/>
- Loki HTTP API: <https://grafana.com/docs/loki/latest/reference/loki-http-api/>
- Grafana dashboard JSON model:
  <https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/view-dashboard-json-model/>
- Sentry issue/event API: <https://docs.sentry.io/api/events/>
- OpenTelemetry file exporter:
  <https://opentelemetry.io/docs/specs/otel/protocol/file-exporter/>

## Input manifest

`p135.export_manifest.v1` is a strict JSON object with:

- `schema_version`, `manifest_id`, `manifest_version`, `created_at`;
- `root_ref_hash` and `p134_contract_hash`;
- `limits`;
- `artifacts` in lexical `source_id` order;
- `manifest_hash`.

Each artifact has exactly:

- `source_id`, `provider`, `format`, `signal_family`;
- `relative_path`;
- `expected_content_hash`, `expected_bytes`, `expected_records`;
- `authority_receipt_hash`, `authority_capability`;
- `artifact_spec_hash`.

`relative_path` is runtime input and never copied into promoted execution
receipts. It must be UTF-8, relative, component-normalized, contain no empty,
`.` or `..` component, contain no NUL, and remain under the separately supplied
allowlisted root. URLs, URI schemes, drive prefixes, shell metacharacters, and
credential-like components fail closed. The release fixture uses paths under
`evals/p135/input/exports`; production paths are not claimed.

Manifest limits are positive integers, never booleans:

- `max_artifacts`: 1..16;
- `max_file_bytes`: 1..4,194,304;
- `max_total_bytes`: 1..16,777,216;
- `max_records_per_artifact`: 1..10,000;
- `max_total_records`: 1..25,000;
- `max_json_depth`: 1..32;
- `max_json_nodes`: 1..200,000;
- `max_string_bytes`: 1..32,768;
- `max_preview_bytes`: 0..256;
- `max_attributes_per_record`: 0..64;
- `max_line_bytes`: 1..1,048,576.

The manifest's expected byte and record values must also fit both its limits
and the bound P134 decision receipt estimates.

## Filesystem trust boundary

P135 accepts an allowlisted root directory out of band and performs all reads
relative to a securely opened root descriptor.

- Every path component is opened without following symlinks; intermediate
  components must be directories and the final component a regular file.
- Absolute paths, traversal, symlinks, FIFOs, sockets, devices, directories,
  hard-linked files, and files outside the root fail closed.
- Pre-read and post-read file identity, size, and modification metadata must
  match. Replacement, growth, truncation, or mutation during the read fails.
- Reads are capped before allocation and performed in bounded chunks. The
  observed SHA-256 and byte count must match the manifest and P134 estimate.
- UTF-8 is strict. JSON duplicate keys, non-finite numbers, excessive depth,
  nodes, strings, lines, attributes, or records fail closed.

These controls prove bounded local file access, not file origin authenticity.
The receipt therefore records content and path-reference hashes, not a claim
that a provider produced the file.

## Normalized evidence envelope

Every successful artifact produces `p135.normalized_evidence_bundle.v1` with:

- `schema_version`, `source_id`, `provider`, `format`, `signal_family`;
- `artifact_content_hash`, `artifact_bytes`, `record_count`;
- `records` in deterministic source order;
- `bundle_hash`.

Every `p135.normalized_evidence_record.v1` contains exactly:

- `schema_version`, `evidence_id`, `ordinal`, `provider`, `format`;
- `p120_record`, a complete record accepted by
  `validate_normalized_record`, including `system_id`, `entity_ref`,
  `ingested_at`, `window`, `labels`, `redaction_receipt`, exact-zero P120
  `authority_counters`, `evidence_state`, `denominator_visible`, and `raw_ref`;
- `content_hash`, `redacted_preview`, `risk_flags`;
- `source_record_hash`, `execution_receipt_ref`, `record_hash`.

P135-specific provenance wraps rather than replaces the P120 envelope. The
embedded P120 record is independently validated and always denominator-visible.
Service and signal references are bounded redacted labels; unknown or sensitive
attribute values are hashed. Log bodies, exception text, queries, dashboard
expressions, and span attributes are untrusted evidence. They are never treated
as instructions. Only a redacted UTF-8 preview bounded by
`max_preview_bytes` is persisted; the complete selected content is represented
by `content_hash`. Credential-like material, control characters, prompt-like
action text, and oversized content set closed risk flags and are excluded from
the preview where necessary.

Provider payloads are extensible, so unknown provider fields are ignored after
global structural budgets are checked. P135's own manifests, receipts,
ledgers, bundles, release evidence, and reviews remain exact-key schemas.

## Execution receipt and ledger

`p135.export_execution_receipt.v1` binds:

- manifest, artifact-spec, P134 contract, P134 decision, root-reference,
  path-reference, and artifact-content hashes;
- provider, adapter version, signal family, bytes read, records normalized,
  started/completed timestamps supplied by the caller;
- pre/post file identity hashes and normalized bundle hash;
- the prior execution receipt hash;
- exact authority counters and the receipt hash.

The receipt contains no absolute path, credential, endpoint, header, or raw
payload. `started_at` and `completed_at` are caller-supplied UTC second values;
the service does not read wall time. Completion may not precede start.

`p135.export_execution_ledger.v1` stores immutable successful receipts and
counters for succeeded reads, bytes read, and normalized records. A success key
is the hash of contract, authority receipt, artifact spec, adapter version, and
observed content. Reattaching an apparently identical artifact must securely
re-open, re-read, and re-hash the current file before returning the original
receipt and byte-identical success ledger with an out-of-band
`duplicate=true`. The duplicate wrapper discloses a validation read and never
claims cache state as fresh observation. Reusing a source ID with changed spec
or content raises a closed conflict.

A failure before any content byte is read emits only a fail-closed attempt
result. Any parser, redaction, provenance, or record-budget failure after a
successful content read emits a hash-bound
`p135.denominator_failure_bundle.v1` containing at least one full P120
`evidence_state=fail_closed`, `denominator_visible=true` record plus a failed
execution receipt. It is evaluation evidence, not a successful attachment, and
cannot be silently dropped from the denominator. Actual stat/open/read/byte and
record activity is disclosed in observation activity evidence.

Ledger validation recomputes every receipt ID, hash link, counter transition,
bundle hash, source uniqueness rule, and exact-zero forbidden authority field.
Rehashing fabricated counters or a forged bundle cannot make it valid.

## Counter separation

Every P135 receipt, bundle, ledger, and release artifact carries two exact maps:

- `authority_counters`: every `P121_AUTHORITY_COUNTER_KEYS` key exactly once,
  each an integer zero.
- `observation_activity_counters`: exactly `local_stat_count`,
  `local_file_open_count`, `local_file_read_count`, `local_bytes_read`,
  `local_records_parsed`, and `duplicate_validation_read_count`, each a
  non-negative integer and never a boolean.

Release authority evidence additionally carries exact-zero
`provider_call_count`, `live_connector_call_count`, `network_call_count`,
`dns_lookup_count`, `socket_call_count`, `credential_read_count`,
`environment_read_count`, `subprocess_launch_count`, `shell_execution_count`,
`signal_count`, `delivery_count`, `remediation_count`,
`staging_mutation_count`, `production_mutation_count`, and
`operator_replacement_count`. Missing, unknown, boolean, nonzero, or misplaced
counters fail closed.

Environment strings and target labels such as production/staging are untrusted
data, not proof of attachment. They are hashed in normalized references unless
explicitly allowlisted as non-sensitive fixture labels. Release claim scanning
blocks assertions of live production/staging proof or attachment.

## Canonical evaluation

The P135 release runner uses five provider-shaped artifacts plus adversarial
copies under `evals/p135/input`. Its fixed denominator is 30 principal cases:

- 5 successful provider attachments, including one single-signal OTLP file;
- 1 deterministic duplicate;
- 10 manifest/authority/budget/path failures;
- 9 parser/redaction/provenance failures;
- 5 tamper/replay/authority failures.

Canonical success requires 30/30, one success for each provider, exact
idempotency, prompt-injection-as-data handling, and zero forbidden authority.

## Release gates

- Independent plan and code reviews have zero unresolved P0/P1/P2 findings.
- Dedicated tests, Ruff, Mypy, and the full repository verification pass.
- Exactly 30/30 canonical cases pass.
- All five adapter versions produce semantically valid normalized bundles.
- Every successful read is bound to a current allowed P134 OA1 receipt and
  matching content/byte/record estimates.
- Promoted ledgers and bundles are independently revalidated from source-bound
  artifacts; all source hashes are current.
- Runtime local file read counts equal successful reads plus disclosed duplicate
  validation reads and post-read failure reads. Provider, socket, DNS, HTTP,
  credential, environment,
  subprocess, shell, signal, delivery, action, remediation, staging mutation,
  production mutation, and operator-replacement counts are exact zero.
- Canonical wall time is at most 30 seconds, CPU at most 10 seconds, and peak
  resident memory at most 96 MiB.
- Release status is exactly
  `p135_provider_shaped_export_attachment_qualified`.

## Non-goals

- No live provider/API attachment, credentials, auth, webhooks, polling, tailing,
  watch mode, notification delivery, remediation, or production mutation.
- No proof that an export came from the named provider; only declared shape,
  local path confinement, and content provenance are proven.
- No LLM judgment or automatic action is introduced here. P135 supplies safer
  evidence to later judgment layers.
- No claim of complete support for every provider version or payload family.

## Delivery slices

1. P135-001: authority bridge and strict manifest.
2. P135-002: secure bounded local artifact reader.
3. P135-003: five versioned provider adapters and normalized evidence schema.
4. P135-004: execution receipts, ledger, idempotency, and tamper validation.
5. P135-005: fixed 30-case evaluation runner and canonical fixtures.
6. P135-006: independent review and release-evidence gate.
7. P135-007: full verification, documentation, Lore commit, and private push.
