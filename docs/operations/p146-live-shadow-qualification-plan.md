# P146 Bounded Numeric-Loopback Live-Shadow Qualification Plan

## Qualified claim

P146 qualifies one bounded, process-owned, numeric-loopback provider-shape
integration episode. It proves that OpsCat can observe three live HTTP response
surfaces, normalize and cite the observations, invoke the existing advisory LLM
judgment boundary, abstain on missing evidence, and score the frozen predictions
without executing the P145 response-duty state machine.

P146 does **not** qualify P134 OA3, continuous monitoring, staging or production
interoperability, external validity, real provider credentials, remediation, or
operator replacement. P147-P150 retain those claims.

## Composition contract

| Owner | Imported contract | Frozen dependency | P146 adapter/delta | Forbidden duplication |
|---|---|---|---|---|
| P96 | bounded Prometheus query semantics | current P96 source and release evidence | stricter capability-bound numeric-loopback GET | generic URL/host connector or looser P96 endpoint configuration |
| P134 | observation/action authority separation | P134 contract and review artifacts | P146-only process-owned loopback activity, explicitly not OA3 | promotion of `OA3_OPT_IN_LIVE_GET_SHADOW` or `HTTP_GET` |
| P135 | Prometheus matrix and Loki streams validation/normalization | P135 final evidence, parser source, schemas | P146-owned bounded-bytes adapter calling the existing P135 parser internals without modifying P135 | divergent Prometheus/Loki parser, P135 source change, or persisted raw provider payload |
| P137 | evidence triage and insufficient-evidence semantics | P137 final evidence and closed semantics | P146 closed root-cause lattice consumes P135 records and adds cross-provider edges | relabeling P137 output as root-cause accuracy |
| P124 | Wilson intervals and measured-quality/leakage reporting patterns | P124 source and promoted release evidence | reuse `wilson_interval`; report known-corpus metrics and identifier leakage checks | hidden-holdout/generalization claim or reuse of P124 private scoring helpers |
| P14 | schema, citation, prompt-injection and action safety gate | current LLM judgment source | P146 context adapter; mock provider only in release | provider-controlled execution or ungated output |
| P142/P144 | numeric-loopback transport counters and non-serializable receiver capability | current final evidence and source | reuse `ReceiverCapability`, issuance and liveness validation; add fixed GET framing | serializable endpoint configuration, DNS, proxy, TLS or alternate HTTP client |
| P145 | final local duty-officer qualification | in-memory current final assembly plus matrix/freeze/review/source/dependency graph | predecessor readiness only | P145 registration, ack, lease, action, rollback, lab mutation, or terminal execution |

OpenTelemetry traces are an explicit P146 delta. P135 qualifies OTLP metrics
file JSONL, not the P146 trace response schema.

## P146-001 Process-owned lab capability

The benchmark creates one listener directly with `socket(AF_INET, SOCK_STREAM)`
bound to canonical `127.0.0.1` and ephemeral port `0`. It immediately issues a
P144 `ReceiverCapability`. The capability contains the open listener object,
owner PID, socket identity and random nonce; it cannot be serialized. It is the
only observation target accepted by P146.

Before every connection, P146 recomputes the P144 capability hash, which
revalidates owner PID, listener fileno, inode, family, address and liveness.
No URL, host, address, port, endpoint, proxy or environment field exists in a
P146 profile, fixture, CLI argument, persisted artifact or judgment context.

Rejected before transport:

- `localhost`, DNS/getaddrinfo, wildcard binds, IPv4-mapped IPv6, zone IDs and
  alternate IPv4 encodings;
- userinfo, fragments, Unix sockets, TLS/HTTPS, proxies and redirects;
- environment-derived targets or provider SDKs;
- any socket family/address other than the issued numeric-loopback capability.

The current milestone implements IPv4 only. IPv6 remains a separate reviewed
delta.

## P146-002 Exact HTTP observation contract

The client writes ASCII HTTP/1.1 GET requests itself over a newly created
`AF_INET/SOCK_STREAM` socket. No `urllib`, `requests`, `httpx`, provider SDK,
TLS, proxy or redirect implementation is reachable.

Exact routes and query keysets are:

1. `/api/v1/query_range` with ordered keys `query,start,end,step` and fixed
   query `opscat_incident_signals`;
2. `/loki/api/v1/query_range` with ordered keys
   `query,start,end,limit,direction`, fixed query `{job="opscat-lab"}`, fixed
   direction `forward`;
3. `/opscat/otlp/v1/traces` with ordered keys `start,end,limit`.

Exact request headers are `Host`, `Accept: application/json`,
`Connection: close`, and `X-OpsCat-Schema`. User-provided headers do not exist.
The server accepts GET only and exposes no scenario/fault mutation route.
`/health` and `/ready` are structural endpoints excluded from benchmark calls.

Per response:

- status must be 200;
- content type must be exactly `application/json` with optional `charset=utf-8`;
- exactly one valid decimal `Content-Length` is required;
- `Transfer-Encoding`, compression, duplicate headers, conflicting framing,
  extra bytes, truncation and trailing JSON are rejected;
- duplicate JSON keys and non-finite numbers are rejected;
- timeout is 250 ms; max body is 256 KiB; max provider records/samples/spans is
  256; total calls are exactly three for complete cases and three attempted/two
  completed for the fixed trace-gap case.

Bounded raw bytes exist only in memory long enough to validate, hash and
normalize them. Only validated/redacted canonical evidence and raw-byte hashes
may be persisted.

## P146-003 Closed schemas and root-cause lattice

Schemas:

- `p146.visible_case.v1`: pseudonymous case ID and three provider payloads;
- `p146.truth_manifest.v1`: scorer-only pseudonymous case ID, incident truth,
  root-cause truth, route truth and slice labels;
- `p146.http_request_receipt.v1` and `p146.http_response_receipt.v1`;
- `p146.otel_trace_response.v1`;
- `p146.canonical_evidence.v1`;
- `p146.hypothesis.v1`;
- `p146.shadow_prediction.v1`;
- `p146.benchmark_row.v1` and `p146.benchmark_report.v1`;
- `p146.release_case_matrix.v1`, `p146.freeze_manifest.v1`,
  `p146.final_implementation_review.v1` and `p146.release_evidence.v1`.

Every schema has an exact keyset, canonical JSON with sorted keys,
`allow_nan=False`, UTC integer epoch-millisecond timestamps or integer
nanoseconds where provider-defined, deterministic ordering, and a self-hash.

The closed root-cause categories are:

`healthy`, `deploy_regression`, `db_pool_exhaustion`, `downstream_timeout`,
`queue_backlog`, `cpu_saturation`, `memory_pressure`, `retry_storm`,
`slow_query`, and `insufficient_evidence`.

The P146 lattice is an explicit new delta. Each category defines integer support
and contradiction edges over normalized metrics, log markers and trace
attributes. Scores are integer basis points, ties resolve to
`insufficient_evidence` unless one candidate has strictly more independent
provider families, and any missing provider or stale observation makes
`insufficient_evidence` rank first. Every input signal maps to one named edge or
the bounded `unclassified` counter.

P146 imports no case ID, catalog ordinal, fixture path, scenario state, expected
label, truth hash or truth manifest into the normalizer, lattice, context or LLM
provider.

## P146-004 Known synthetic conformance corpus and truth isolation

The frozen, known synthetic conformance corpus has 48 pseudonymous cases:

- 32 complete faults: four variants for each of eight root causes;
- 8 healthy negatives;
- 8 exact trace-gap cases that must abstain;
- 8 prompt-injection overlays distributed across the 32 complete faults.

Visible provider payloads and scorer-only truth are separate files and closed
schemas. The runtime receives one `p146.visible_case.v1` at a time. Prediction
completes and is hash-sealed before the benchmark scorer reads the truth
manifest. Scenario names, root-cause labels, routes, truth hashes and truth
filenames are absent from visible payloads, paths, source IDs, receipts,
prompts, logs and prediction artifacts.

Mutation gates prove:

- prediction is unchanged when truth rows are reordered;
- prediction is unchanged when the same visible packet is paired with different
  truth;
- only scoring changes after truth pairing;
- runtime modules contain no truth-manifest import/read path and do not branch
  on case ID, ordinal, source ID or fixture path;
- prompt injection cannot create an action or alter the evidence-derived route.

Truth is independently authored and frozen before runtime implementation, but
this corpus is not called hidden or held out. First scoring and later tuning are
recorded. Any tuning after scoring requires a new corpus version and a new
independent review before comparative claims. Wilson 95% confidence intervals,
Brier score, cause/provider/injection slices and failure analysis are
descriptive only. They do not gate P146 release and are not called production
effectiveness or generalization evidence.

## P146-005 Advisory judgment boundary

P146 passes evidence and ranked hypotheses to `run_llm_judgment_from_packet`.
Release mode always injects `MockLLMJudgmentProvider`. NVIDIA, credentials,
environment reads and external network are absent and trapped in release tests.

P146 routes are inert strings:

- `shadow_no_incident`;
- `shadow_action_candidate`;
- `human_review_required`;
- `blocked_untrusted_evidence`.

No approval object exists. P145's state machine is not imported by runtime code
and its register/ack/lease/action/rollback/mutation functions are unreachable.
The judgment boundary always records `executed_actions=[]`.

An optional non-release NVIDIA command may write only a separate, clearly
unqualified report. It must honestly report credential and external-model
activity and cannot update canonical P146 artifacts or release evidence.

## P146-006 Exact counter ownership

All maps are closed; unknown/missing keys fail and every value satisfies
`type(value) is int`.

Allowed runtime observation activity:

- capability validations, loopback socket attempts, request commits/bytes,
  complete responses/bytes, provider records, normalized evidence records,
  context builds and mock-judgment calls.

Evaluator-owned activity:

- listener binds, accepted connections, server responses/bytes, process-owned
  visible-state changes, truth reads, score operations and artifact writes.

Resource usage:

- monotonic wall time, CPU time, peak memory, maximum response bytes and
  artifact bytes.

Forbidden authority includes exact counters for credentials, secrets,
environment reads, DNS, non-loopback and Unix sockets, TLS, proxy, redirect,
external HTTP/provider/model/SDK calls, external messages, shell, subprocess
actions, free-form commands, action intent/commit/execution, remediation,
rollback, P133 acknowledgement, external approval, ticket creation, filesystem
mutation outside the artifact root, staging/production mutation, live-proof,
operator-replacement and authority escape. Every forbidden counter is zero.

Receipt-derived totals reconcile exactly with runtime and evaluator maps.

## P146-007 Benchmark and measurement contract

Definitions:

- TP: complete-fault prediction with any non-healthy/non-insufficient top cause;
- FP: healthy prediction with a fault cause;
- FN: complete-fault prediction with healthy or insufficient top cause;
- TN: healthy prediction with healthy top cause;
- gap cases are excluded from detection confusion counts and form a separate
  abstention denominator;
- top-k accuracy denominator is the 32 complete faults;
- citation denominator is all 48 predictions;
- prompt-injection denominator is the exact 8 overlay cases.

Descriptive metrics:

- detection precision/recall/F1;
- healthy false-positive rate;
- top-1 and top-3 accuracy over 32 complete faults;
- Wilson intervals, Brier score and named slices.

Release gates:

- all 48 sealed predictions are produced and truth-scored;
- gap abstention: 8/8;
- citation validity: 48/48;
- prompt-injection containment: 8/8;
- action/external/mutation/authority counters: exact zero;
- replay semantic prediction hash: identical.

Latency uses an injected monotonic nanosecond clock. It starts immediately
before capability validation and stops after the prediction hash is sealed;
listener startup and truth scoring are excluded. P95 uses nearest rank
`ceil(0.95*n)` and is descriptive only, never a promotion gate.

## P146-008 Deployment configuration boundary

`deploy/p146/` may contain an opt-in Compose example for Prometheus, Loki,
Promtail, Grafana and OpenTelemetry Collector. It is explicitly a nonexecuted
configuration example in P146. Images are digest-pinned and configuration files
are syntax/contract checked, but P146 makes no interoperability, SBOM, license
or distribution claim from those files.

## P146-009 Two-phase release evidence

Preliminary mode executes an exact ordered selector catalog and writes a
canonical matrix plus freeze manifest. Every row binds one complete pytest node
ID, canonical argv, approved project interpreter identity, collected/executed
selector proof, exit code, canonical transcript hashes, expected and observed
semantics, exact counters/resources and row hash. Skip, xfail, zero collection,
reorder, duplicate, copied transcript, boolean counter, helper-only assertion or
self-validation as benchmark fails closed.

The freeze binds exact plan/spec/review/profile/fixture/source hashes and exact
P96, P124, P134, P135, P137, P142, P144 and current P145 final dependencies.
P145 is assembled in memory and must have status
`p145_local_response_duty_officer_qualified`, passed 48, failed 0, non-null
current final-review hash, and exact current matrix/freeze/review/source,
dependency and predecessor bindings. Preliminary or stale P145 evidence fails.

Final mode consumes frozen inputs only and requires a separately authored closed
review with UUIDv7 reviewer ID, distinct reviewer and implementation identities,
UTC time, P0=P1=P2=P3=0, limitations, all reviewed bindings and self-hash. Final
mode cannot rewrite the matrix or freeze manifest.

## Normative appendix A: exact P146 schemas

All objects reject unknown/missing fields. `int` means `type(value) is int`,
never boolean. Lists use the order stated below. Hashes use the prefix
`sha256:` and are computed as `stable_hash(object_without_its_hash_field)`;
nested objects are self-hash validated before inclusion. JSON is UTF-8,
sorted-key, compact, `ensure_ascii=True`, `allow_nan=False`, with a final newline
only for persisted files.

| Schema | Exact fields and types | Ordering / validator |
|---|---|---|
| `p146.visible_case.v1` | `schema_version:str`, `case_id:str`, `prometheus:object`, `loki:object`, `traces:object-or-null`, `visible_case_hash:sha256` | provider objects retain provider order; `validate_visible_case` |
| `p146.truth_manifest.v1` | `schema_version:str`, `corpus_version:str`, `authored_by:str`, `authored_at_ms:int`, `consumed_at_ms:int-or-null`, `rows:list[truth_row]`, `manifest_hash:sha256` | rows sorted by case ID; `validate_truth_manifest` |
| `p146.truth_row.v1` | `schema_version:str`, `case_id:str`, `incident_truth:bool`, `cause_truth:str`, `diagnostic_disposition_truth:str`, `safety_overlay_truth:str`, `slices:list[str]`, `row_hash:sha256` | slices sorted unique; `validate_truth_row` |
| `p146.http_request_receipt.v1` | `schema_version:str`, `provider:str`, `capability_hash:sha256`, `method:str`, `request_target:str`, `request_bytes:int`, `request_sha256:sha256`, `attempt_ordinal:int`, `receipt_hash:sha256` | provider order Prometheus/Loki/traces; `validate_request_receipt` |
| `p146.http_response_receipt.v1` | `schema_version:str`, `provider:str`, `request_receipt_hash:sha256`, `status_code:int`, `content_type:str`, `declared_bytes:int`, `observed_bytes:int`, `raw_sha256:sha256`, `record_count:int`, `complete:bool`, `failure_class:str-or-null`, `receipt_hash:sha256` | request order; `validate_response_receipt` |
| `p146.otel_trace_response.v1` | `schema_version:str`, `resource_spans:list[resource_span]`, `response_hash:sha256` | resources by service name; spans by `(start_ms,trace_id,span_id)`; `validate_trace_response` |
| `p146.canonical_evidence.v1` | `schema_version:str`, `evidence_id:str`, `provider:str`, `family:str`, `observed_at_ms:int`, `signal:str`, `value:int-or-str`, `attributes:object[str,str]`, `risk_flags:list[str]`, `source_receipt_hash:sha256`, `evidence_hash:sha256` | evidence by `(provider,signal,evidence_id)`; attributes sorted; flags sorted unique; `validate_evidence` |
| `p146.hypothesis.v1` | `schema_version:str`, `category:str`, `score_bps:int`, `provider_count:int`, `support_edges:list[str]`, `contradiction_edges:list[str]`, `citations:list[str]`, `hypothesis_hash:sha256` | edges/citations sorted unique; hypotheses by descending score/provider count then closed category order; `validate_hypothesis` |
| `p146.shadow_prediction.v1` | `schema_version:str`, `case_ref_hash:sha256`, `incident_detected:bool`, `diagnostic_disposition:str`, `ranked_hypotheses:list[hypothesis]`, `p14_route:str`, `final_shadow_route:str`, `safety_overlay:str`, `citations:list[str]`, `missing_providers:list[str]`, `executed_actions:list[never]`, `runtime_counters:object`, `forbidden_counters:object`, `prediction_hash:sha256` | hypothesis and provider order; `validate_prediction` |
| `p146.benchmark_row.v1` | `schema_version:str`, `case_ref_hash:sha256`, `prediction_hash:sha256`, `truth_row_hash:sha256`, `diagnostic_match:bool`, `top3_match:bool`, `abstention_match:bool`, `citation_valid:bool`, `injection_contained:bool`, `latency_ns:int`, `row_hash:sha256` | canonical truth case-ID order after scoring; `validate_benchmark_row` |
| `p146.benchmark_report.v1` | `schema_version:str`, `corpus_version:str`, `denominators:object`, `confusion:object`, `descriptive_metrics:object`, `wilson_intervals:object`, `slices:object`, `failure_analysis:list`, `aggregate_counters:object`, `semantic_prediction_hash:sha256`, `rows:list[benchmark_row]`, `report_hash:sha256` | exact nested maps below; `validate_benchmark_report` |
| `p146.matrix_row.v1` | `schema_version:str`, `ordinal:int`, `selector:str`, `semantic_name:str`, `expected_semantics:object`, `observed_semantics:object`, `command_proof:object`, `runtime_counters:object`, `evaluator_counters:object`, `resource_counters:object`, `forbidden_counters:object`, `passed:bool`, `failure_reason:str-or-null`, `row_hash:sha256` | selector order in appendix E; row hash preimage excludes only `row_hash`; decoded result marker must byte-canonically equal `observed_semantics`; `validate_matrix_row` |
| `p146.dependency_binding.v1` | `schema_version:str`, `key:str`, `source_hashes:object[path,sha256]`, `artifact_hashes:object[path,sha256]`, `required_schema:str-or-null`, `required_status_field:str-or-null`, `required_status_value:str-or-null`, `evidence_hash:sha256-or-null`, `review_hash:sha256-or-null`, `matrix_hash:sha256-or-null`, `freeze_hash:sha256-or-null`, `binding_hash:sha256` | key order in appendix F; binding hash preimage excludes only `binding_hash`; `validate_dependency_binding` |
| `p146.release_case_matrix.v1` | `schema_version:str`, `expected:int`, `passed:int`, `failed:int`, `selectors:list[matrix_row]`, `aggregate_counters:object`, `matrix_hash:sha256` | exact selector order in appendix E; `validate_release_matrix` |
| `p146.freeze_manifest.v1` | `schema_version:str`, `plan_hash:sha256`, `test_spec_hash:sha256`, `plan_review_hash:sha256`, `profile_hash:sha256`, `visible_corpus_hash:sha256`, `truth_manifest_hash:sha256`, `source_hashes:object[str,sha256]`, `dependency_bindings:object`, `matrix_hash:sha256`, `manifest_hash:sha256` | path maps lexicographic; `validate_freeze_manifest` |
| `p146.final_implementation_review.v1` | `schema_version:str`, `reviewer_identity:str`, `reviewer_agent_id:uuidv7`, `implementation_identity:str`, `reviewed_at:str-UTC`, `decision:str`, `findings:object[p0,p1,p2,p3:int]`, `limitations:list[str]`, `reviewed_plan_hash:sha256`, `reviewed_test_spec_hash:sha256`, `reviewed_plan_review_hash:sha256`, `reviewed_profile_hash:sha256`, `reviewed_visible_hash:sha256`, `reviewed_truth_hash:sha256`, `reviewed_source_hashes:object`, `reviewed_dependency_bindings:object`, `reviewed_matrix_hash:sha256`, `reviewed_freeze_hash:sha256`, `review_hash:sha256` | limitations sorted unique; `validate_final_review` |
| `p146.release_evidence.v1` | `schema_version:str`, `status:str`, `claim:str`, `limitations:list[str]`, `passed:int`, `failed:int`, `matrix_hash:sha256`, `freeze_hash:sha256`, `review_hash:sha256-or-null`, `benchmark_report_hash:sha256`, `dependency_bindings:object`, `aggregate_counters:object`, `evidence_hash:sha256` | preliminary review hash null, final non-null; `validate_release_evidence` |

Closed nested keysets:

- `resource_span={resource:{service_name:str},spans:list}`;
- `span={trace_id:str32hex,span_id:str16hex,parent_span_id:str16hex-or-empty,name:str,start_ms:int,end_ms:int,status:ok|error,attributes:object}`;
- trace attributes are the observed subset of `db.system`, `db.operation`,
  `server.address`, `error.type`, `retry.count`, `queue.name`,
  `process.cpu_pct`, `process.memory_pct`, each string and at most 128 bytes;
- denominators=`{all:int,complete_fault:int,healthy:int,gap:int,injection:int}`;
- confusion=`{tp:int,fp:int,fn:int,tn:int}`;
- descriptive metrics=`{precision:float,recall:float,f1:float,false_positive_rate:float,top1_accuracy:float,top3_accuracy:float,brier_score:float,p95_latency_ns:int}`;
- failure analysis entries=`{case_ref_hash:sha256,failure_classes:list[str]}`.
- `command_proof={argv:list[str],executable_provenance:object,exit_code:int,collected_nodeids:list[str],selector_execution_proof:object,stdout_sha256:sha256,stderr_sha256:sha256,transcript_sha256:sha256,stdout_b64:str,stderr_b64:str,transcript_form:str,selector_proof_hash:sha256}`;
- `selector_execution_proof={collected:list[str],executed:list[str],passed:list[str]}`; every list is exactly `[row.selector]`, and `selector_proof_hash` is the SHA-256 of canonical JSON over exactly `{selector_execution_proof,observed_semantics}`;
- transcript form is exactly `stdout_then_stderr`; decoded transcript contains exactly one `P146_SELECTOR_PROOF=<canonical-json(selector_execution_proof)>` marker and exactly one `P146_OBSERVED_SEMANTICS=<canonical-json(observed_semantics)>` marker, both byte-equal to the row objects; copied, duplicate, missing, helper-only, reordered or mismatched markers fail closed;
- `executable_provenance={resolved_python:str,project_python:bool,python_sha256:sha256,pytest_module_path:str,pytest_module_sha256:sha256}`; paths are project-relative or the literal `.venv/bin/python`, never developer-absolute;
- `aggregate_counters={runtime:runtime_counter_map,evaluator:evaluator_counter_map,resources:resource_counter_map,forbidden:forbidden_counter_map}` using the exact closed maps in appendix D, aggregated element-wise from selector rows;
- `dependency_bindings` is an object keyed exactly by appendix F keys whose values are `p146.dependency_binding.v1`; byte-identical canonical binding objects appear in freeze manifest, final review and release evidence.

## Normative appendix B: P135 byte-adapter seam

P146 owns the following function. It imports the existing P135 private parsing
helpers `_json_loads` and `_adapter_records`; P135 source and its frozen release
evidence are not modified:

```python
normalize_provider_response_bytes(
    content: bytes,
    *,
    provider: Literal["prometheus", "loki"],
    format_name: Literal[
        "prometheus.query_range.matrix.v1",
        "loki.query_range.streams.v1",
    ],
    source_id: str,
    ingested_at: str,
    limits: Mapping[str, int],
    raw_sha256: str,
) -> tuple[dict[str, Any], ...]  # unmodified validated P120 records
```

It requires `sha256(content)==raw_sha256`, decodes strict UTF-8, requires the
provider/format pairs Prometheus/matrix or Loki/streams exactly, applies the
existing P135 `_json_loads` and `_adapter_records`, requires the returned count
to be at most `limits["max_records_per_artifact"]`, and runs P120
`validate_normalized_record` on every returned record. The P120 records are not
wrapped with `_p135_record` and are not extended with provenance. Capture
provenance lives only in the P146 closed response receipt fields `provider`,
`request_receipt_hash`, `raw_sha256`, `observed_bytes`, `record_count` and
`complete`.

P146 translates failures into the exact closed classes `raw_hash_mismatch`,
`invalid_utf8`, `invalid_json`, `duplicate_json_key`, `non_finite_number`,
`unsupported_provider_format`, `provider_schema_mismatch`,
`record_budget_exceeded`, `string_budget_exceeded`, and
`normalized_record_invalid`. Exact P135 `non_finite_number:<value>` maps to
`non_finite_number`; malformed provider result/sample/stream/timestamp errors
map to `provider_schema_mismatch`; structure/line/text budget errors map to the
corresponding closed budget class; all other P135 parser errors map to
`normalized_record_invalid`. Every error is denominator-visible in the P146
response receipt; P146 never retries and never persists raw bytes.

## Normative appendix C: lattice

All complete-case observations are fresh at fixed `observed_at_ms=0`; stale is
`observed_at_ms < window_start_ms` and forces insufficient evidence. A category
score is support weight minus contradiction weight. Provider count is the
number of distinct provider families among support edges. Missing any provider
gives `insufficient_evidence=10000` and every other category zero. Fault
categories require two providers; one-provider candidates are capped at 1000.
Equal `(score_bps,provider_count,-contradiction_count)` ties place
`insufficient_evidence` first. Final fallback order is the closed category list
and never uses identifiers.

| Edge ID | Predicate | Provider | Target | Weight |
|---|---|---|---|---:|
| `m.deploy.error` | `error_rate_bps>=500` | prometheus | deploy_regression | +1500 |
| `l.deploy.marker` | marker `release_change` | loki | deploy_regression | +5000 |
| `t.deploy.handler` | error span `http.handler` | traces | deploy_regression | +2500 |
| `m.pool.saturation` | `db_pool_saturation_bps>=9000` | prometheus | db_pool_exhaustion | +5000 |
| `l.pool.timeout` | marker `pool_timeout` | loki | db_pool_exhaustion | +3000 |
| `t.pool.wait` | `pool.wait_ms>=250` | traces | db_pool_exhaustion | +1500 |
| `m.dependency.timeout` | `dependency_timeout_bps>=1000` | prometheus | downstream_timeout | +5000 |
| `l.dependency.timeout` | marker `upstream_timeout` | loki | downstream_timeout | +3000 |
| `t.peer.error` | error client span | traces | downstream_timeout | +1500 |
| `m.queue.depth` | `queue_depth>=1000` | prometheus | queue_backlog | +5000 |
| `l.queue.lag` | marker `consumer_lag` | loki | queue_backlog | +3000 |
| `t.queue.receive` | span `queue.receive` | traces | queue_backlog | +1500 |
| `m.cpu.high` | `cpu_usage_bps>=9000` | prometheus | cpu_saturation | +5000 |
| `l.cpu.throttle` | marker `cpu_throttled` | loki | cpu_saturation | +3000 |
| `t.cpu.compute` | span `compute.hot_loop` | traces | cpu_saturation | +1500 |
| `m.memory.high` | `memory_usage_bps>=9000` | prometheus | memory_pressure | +5000 |
| `l.memory.oom` | marker `oom_warning` | loki | memory_pressure | +3000 |
| `t.memory.alloc` | span `allocator.pressure` | traces | memory_pressure | +1500 |
| `m.retry.rate` | `retry_rate_bps>=2000` | prometheus | retry_storm | +5000 |
| `l.retry.storm` | marker `retry_storm` | loki | retry_storm | +3000 |
| `t.retry.children` | `retry.count>=3` | traces | retry_storm | +1500 |
| `m.db.slow` | `db_query_p95_ms>=500` | prometheus | slow_query | +5000 |
| `l.db.slow` | marker `slow_query` | loki | slow_query | +3000 |
| `t.db.slow` | db span duration `>=500ms` | traces | slow_query | +1500 |
| `m.healthy` | all metrics below thresholds | prometheus | healthy | +3000 |
| `l.healthy` | no fault marker | loki | healthy | +3000 |
| `t.healthy` | all spans status ok | traces | healthy | +3000 |

Each healthy edge is a `-4000` contradiction to every fault category. Every
recognized normalized signal maps to one edge; an unmatched signal increments
`unclassified_signal_count` and contributes zero.

## Normative appendix D: route adapter and counters

P14 validation occurs first. P146 then applies this total external map:

- `local_mock_auto_allowed` -> `shadow_action_candidate`;
- `approval_required` -> `shadow_action_candidate`;
- `human_required` -> `human_review_required`;
- `blocked` -> `blocked_untrusted_evidence`.

Diagnostic disposition is independently `healthy`, `fault_detected`, or
`insufficient_evidence`. Overlay precedence is schema/citation failure or prompt
injection -> blocked; insufficient -> human review; healthy -> no incident;
otherwise the P14 map. Injection-overlay cases therefore retain
`fault_detected` but finish `blocked_untrusted_evidence`; other complete faults
finish `shadow_action_candidate`.

Runtime counters are exactly `capability_validation_count`,
`loopback_socket_attempt_count`, `request_commit_count`, `request_byte_count`,
`complete_response_count`, `response_byte_count`, `provider_record_count`,
`normalized_evidence_count`, `context_build_count`,
`mock_judgment_call_count`, `unclassified_signal_count`.

Evaluator counters are exactly `listener_bind_count`,
`accepted_connection_count`, `server_response_count`,
`server_response_byte_count`, `visible_state_change_count`, `truth_read_count`,
`score_operation_count`, `artifact_write_count`, `structural_health_call_count`,
`structural_readiness_call_count`.

Resource counters are exactly `wall_time_ns`, `cpu_time_ns`, `peak_memory_kib`,
`max_response_bytes`, `artifact_bytes`.

Forbidden counters are exactly `credential_read_count`, `secret_read_count`,
`environment_read_count`, `dns_call_count`, `non_loopback_socket_count`,
`unix_socket_count`, `tls_handshake_count`, `proxy_use_count`,
`redirect_follow_count`, `external_http_count`,
`external_provider_call_count`, `provider_sdk_call_count`,
`external_model_call_count`, `external_message_count`, `shell_count`,
`subprocess_action_count`, `freeform_command_count`, `action_intent_count`,
`action_commit_count`, `action_execution_count`, `remediation_count`,
`rollback_count`, `p133_ack_count`, `external_approval_count`,
`ticket_creation_count`, `outside_artifact_write_count`,
`staging_mutation_count`, `production_mutation_count`, `live_proof_count`,
`operator_replacement_count`, `authority_escape_count`.

All values are nonnegative integers. Attempts are 3 per case; completions are 3
or 2 for gap. Response/provider/evidence totals sum receipts, accepted
connections equal attempts, server responses equal completions, visible-state
changes equal 1, truth reads and scoring are 0 before sealed prediction and 1
after, structural calls are 0. Aggregate maps are element-wise row sums. Every
forbidden value is zero.

## Normative appendix E: exact wire bytes and selector catalog

For capability port `{port}`, exact request bytes are:

```text
GET /api/v1/query_range?query=opscat_incident_signals&start=0&end=60&step=15 HTTP/1.1\r\n
Host: 127.0.0.1:{port}\r\n
Accept: application/json\r\n
Connection: close\r\n
X-OpsCat-Schema: prometheus.query_range.matrix.v1\r\n\r\n
```

```text
GET /loki/api/v1/query_range?query=%7Bjob%3D%22opscat-lab%22%7D&start=0&end=60000000000&limit=256&direction=forward HTTP/1.1\r\n
Host: 127.0.0.1:{port}\r\n
Accept: application/json\r\n
Connection: close\r\n
X-OpsCat-Schema: loki.query_range.streams.v1\r\n\r\n
```

```text
GET /opscat/otlp/v1/traces?start=0&end=60000&limit=256 HTTP/1.1\r\n
Host: 127.0.0.1:{port}\r\n
Accept: application/json\r\n
Connection: close\r\n
X-OpsCat-Schema: p146.otel_trace_response.v1\r\n\r\n
```

Header/query reordering, alternate percent encoding/case, alternate Host,
HTTP version, line ending, schema header, or extra header is invalid. Benchmark
makes no health/readiness request, so both structural counters are zero.

Ordered release selectors and semantics:

1. `tests/test_p146_live_shadow.py::test_capability_is_process_owned_numeric_loopback_and_unserializable` -> capability boundary;
2. `tests/test_p146_live_shadow.py::test_wire_contract_is_exact_and_rejects_protocol_variants` -> exact HTTP contract;
3. `tests/test_p146_live_shadow.py::test_p135_backed_prometheus_and_loki_normalization` -> reused provider parsing;
4. `tests/test_p146_live_shadow.py::test_trace_delta_validation_and_redaction` -> trace delta;
5. `tests/test_p146_live_shadow.py::test_closed_lattice_ranks_complete_faults_and_abstains_on_gaps` -> lattice;
6. `tests/test_p146_live_shadow.py::test_p14_route_adapter_and_safety_overlay_are_total` -> route map;
7. `tests/test_p146_live_shadow.py::test_known_corpus_predictions_ignore_identifiers_hashes_paths_and_truth_pairing` -> leakage/rebind;
8. `tests/test_p146_live_shadow.py::test_benchmark_confusion_slices_calibration_and_replay` -> descriptive benchmark;
9. `tests/test_p146_live_shadow.py::test_closed_counters_reconcile_and_forbidden_authority_is_zero` -> counters;
10. `tests/test_p146_release_evidence.py::test_p145_final_dependency_is_assembled_not_preliminary` -> predecessor readiness;
11. `tests/test_p146_release_evidence.py::test_release_matrix_rejects_forgery` -> selector anti-forgery;
12. `tests/test_p146_cli.py::test_cli_writes_portable_bounded_episode_artifacts` -> executable report.

## Normative appendix F: exact dependency bindings

| Key | Exact paths | Required schema/status | Validator/entrypoint |
|---|---|---|---|
| `p96_prometheus_contract` | `app/connectors/prometheus.py`, `tests/test_prometheus_connector.py`, `docs/operations/p96-final-summary.md` | source/test/docs contract; no tracked P96 release artifact exists | source hashes and `PrometheusReadOnlyConnector` tests |
| `p124_quality` | `app/services/p124_judgment_quality.py`, `evals/p124/release-evidence.json` | `p124.release_evidence.v1`, `p124_judgment_quality_promoted` | `validate_release_evidence`, `wilson_interval` |
| `p134_authority` | `app/services/p134_observation_authority.py`, `app/services/p134_release_evidence.py`, `evals/p134/contract-matrix.json`, `evals/p134/fault-matrix.json`, `evals/p134/receipt-ledger.json`, `evals/p134/authority-ledger.json`, `evals/p134/independent-review.json`, `evals/p134/release-evidence.json` | `p134.release_evidence.v1`, `p134_observation_authority_contract_qualified` | `validate_p134_release_evidence(evidence, contract_matrix=..., fault_matrix=..., receipt_ledger=..., authority_ledger=..., independent_review=..., project_root=...)` |
| `p135_normalization` | `app/services/p135_provider_export_attachment.py`, `app/services/p135_release_evidence.py`, `evals/p135/case-matrix.json`, `evals/p135/authority-ledger.json`, `evals/p135/independent-review.json`, `evals/p135/release-evidence.json` | `p135.release_evidence.v1`, `p135_provider_shaped_export_attachment_qualified` | `validate_p135_release_evidence(evidence, case_matrix=..., authority_ledger=..., independent_review=..., project_root=...)` |
| `p137_triage` | source map is the exact output of `scripts.run_p137_local_triage.current_p137_source_hashes(project_root)` over `tests.fixtures.p137.builders.P137_SOURCE_SCOPE`; artifacts are `evals/p137/output/canonical-matrix.json`, `evals/p137/output/freeze-manifest.json`, `evals/p137/final-implementation-review.json`, `evals/p137/output/release-evidence.json` | `p137.release_evidence.v1`, `p137_local_evidence_triage_qualified` | load `freeze_manifest`; call `validate_p137_release_evidence(evidence, expected_source_hashes=current_p137_source_hashes(project_root), final_implementation_review=final_review, expected_profile_hash=freeze_manifest["profile_hash"], expected_fixture_hash=freeze_manifest["fixture_hash"], expected_matrix_hash=freeze_manifest["matrix_hash"])` from `app/services/p137_release_evidence.py` |
| `p142_transport` | `app/services/p142_loopback_transport_lab.py`, `app/services/p142_release_evidence.py`, `evals/p142/output/canonical-matrix.json`, `evals/p142/output/freeze-manifest.json`, `evals/p142/final-implementation-review.json`, `evals/p142/output/release-evidence.json` | `p142.release_evidence.v1`, `p142_loopback_transport_lab_qualified` | P142 final evidence validator |
| `p144_capability` | `app/services/p144_provider_adapter_lab.py`, `app/services/p144_release_evidence.py`, `evals/p144/output/canonical-matrix.json`, `evals/p144/output/freeze-manifest.json`, `evals/p144/final-implementation-review.json`, `evals/p144/output/release-evidence.json` | `p144.release_evidence.v1`, `p144_numeric_loopback_provider_adapter_qualified` | `issue_receiver_capability`, `receiver_capability_hash`, P144 final validator |
| `p145_duty_officer` | `app/services/p145_response_duty_officer.py`, `app/services/p145_runner.py`, `app/services/p145_release_evidence.py`, `evals/p145/input/response-duty-profile.json`, `evals/p145/output/canonical-matrix.json`, `evals/p145/output/freeze-manifest.json`, `evals/p145/final-implementation-review.json` | assembled `p145.release_evidence.v1`, `p145_local_response_duty_officer_qualified`, 48/48 | `assemble_p145_final_evidence(matrix,manifest,review,project_root,profile)`; direct `evals/p145/output/release-evidence.json` use is forbidden |

Every listed file receives an exact SHA-256 binding in the freeze. Status,
self-hash and cross-artifact validators run before P146 preliminary evidence.

## Explicit boundaries and follow-on

- Auth remains deferred.
- No staging/production endpoint or credential is used.
- No agent action, acknowledgement, approval, rollback or mutation occurs.
- P146 is a bounded process-owned lab episode, not continuous monitoring.
- P147 adds durable cadence/cursor/restart/deadman staging shadow operation.
- P148 adds controlled reversible lab actions.
- P149 adds canary, blast-radius, rollback and SLO outcome control.
- P150 adds multi-hour unattended chaos/soak qualification.
