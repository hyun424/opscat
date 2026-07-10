# P105 G006 Source-Expansion Amendment

Status: planning only. This amendment repairs the G006/P105-RQ source-expansion
handoff at HEAD `fba7e87`. It changes no production or test code and does not
change any P105 floor, metric threshold, or P106 gate.

## Non-Negotiable Contract

- Unsupported, ambiguous, unreviewed, parser-failed, or unmapped rows are
  `unsupported_family` and count as zero rows, positives, incident groups,
  source tuples, coverage, or floor credit.
- Family authority comes only from the reviewed source registry plus release
  eligibility manifest. File names, ordinals, partitions, labels, scores,
  floor deficits, or heuristic metric names are never family authority.
- Sampling and partition assignment complete before any private label or
  injection-ledger join.
- Coverage is the union of observed, evaluable timestamp intervals. It is
  never a top-level duration, row count, fixed four-day constant, accelerated
  logical clock, or floor-sized interval.
- The source and harness programs below are immutable inputs. Executors may not
  change salts, schedules, rates, windows, thresholds, or cohort mappings after
  reading labels or floor results. A deficient run stays locked and adds an
  independently reviewed honest source in a later amendment.

The unchanged floors remain:

| Scope | Evaluated | Non-abstained | Positives | Incident groups | Coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| Held-out, per family | 30 | 24 | 6 | 4 | 2.0 service-days |
| Real-derived shadow, per family | 20 | 16 | 4 | 3 | 1.0 service-day |

Source diversity remains at least three canonical source tuples across
real-derived P32/P41/P44 and reviewed expansion inputs, no tuple may contribute
more than 0.60 of a family's real-derived rows, and global coverage remains at
least 7.0 service-days.

## Reviewed Registry and Eligibility Producer

Owner: P105-023 implements and tests the future producer
`scripts/build_p105_source_registry.py`. P105-028 invokes it during the actual
source run and owns downstream materializer consumption. No adapter or harness
writes final eligibility directly.

Canonical output paths:

```text
/tmp/opscat-p105-source-expansion/p105-reviewed-source-registry.json
/tmp/opscat-p105-source-expansion/p105-source-review-ledger.json
/tmp/opscat-p105-source-expansion/p105-source-eligibility-manifest.json
```

Exact producer command:

```bash
SOURCE_DATE_EPOCH=1710002000 \
uv run --no-sync --extra dev python scripts/build_p105_source_registry.py \
  --candidate-manifest evals/telemetry/replay/p32_replay_pack.json \
  --candidate-manifest evals/real_datasets/raw/p41_sources.json \
  --candidate-manifest /tmp/opscat-p105-reviewed-p44/p44-reviewed-local-manifest.json \
  --candidate-manifest /tmp/opscat-p105-reviewed-dejavu-a1/p105-dejavu-a1-reviewed-local-manifest.json \
  --candidate-manifest /tmp/opscat-p105-queue-harness/p105-queue-harness-manifest.json \
  --candidate-manifest /tmp/opscat-p105-deploy-harness/p105-deploy-harness-manifest.json \
  --review-ledger /tmp/opscat-p105-source-expansion/p105-source-review-ledger.json \
  --output-registry /tmp/opscat-p105-source-expansion/p105-reviewed-source-registry.json \
  --output-eligibility /tmp/opscat-p105-source-expansion/p105-source-eligibility-manifest.json \
  --created-at 2024-03-09T16:33:20Z \
  --schema-version p105.source-registry.v1 \
  --fail-on-unreviewed-counting-source
```

The registry root schema is exactly:

```text
schema_version: "p105.source-registry.v1"
created_at: RFC3339 UTC equal to SOURCE_DATE_EPOCH
command_argv: ordered string array with no shell reconstruction
command_argv_sha256: lowercase SHA-256 of canonical JSON command_argv
review_ledger_path: normalized path
review_ledger_sha256: lowercase SHA-256
sources: array sorted by source_key
registry_sha256: SHA-256 of canonical JSON excluding registry_sha256
```

Every `sources[]` entry is exact and closed to unknown fields:

```text
source_key: stable string
source_system: stable string
source_dataset: stable string
source_family_candidate: database|queue|deploy|unsupported_family
source_manifest_path: normalized path
source_manifest_sha256: lowercase SHA-256
source_content_hashes: non-empty sorted array of {path, sha256}
adapter_or_harness: {name, version, command_argv, command_argv_sha256}
created_at: RFC3339 UTC
license: {name, url, citation_text, redistribution_status}
privacy: {review_status, reviewer_id, reviewed_at, redaction_status, notes}
provenance_sha256: lowercase SHA-256 binding all fields above
```

The review ledger contains one decision per `source_key` with
`reviewer_id`, `reviewed_at`, `decision=approved|rejected`, `license_decision`,
`privacy_decision`, `family_authority_decision`, `source_manifest_sha256`, and
`review_signature_sha256`. The registry producer fails if an approved source's
manifest hash differs from the reviewed hash.

The eligibility root is `p105.source-eligibility.v1`, repeats `created_at`,
`command_argv`, `command_argv_sha256`, `registry_sha256`, and
`review_ledger_sha256`, and has `entries[]` sorted by
`(source_key, source_window_id)`. Each entry contains:

```text
source_key
source_window_id
source_manifest_sha256
materialized_record_sha256
pre_label_partition_id
family_candidate
family_authority_source
eligible_for_release_floor: boolean
unsupported_family_reason: nullable enum
coverage_interval_ids: sorted array
private_ledger_path
private_ledger_sha256
label_join_phase: "after_sampling_and_partition"
adapter_or_parser_version
privacy_license_registry_sha256
provenance_sha256
```

Allowed `unsupported_family_reason` values are `unreviewed_source`,
`license_rejected`, `privacy_rejected`, `parser_failed`, `predicate_unmapped`,
`missing_private_ledger`, `missing_partition`, `missing_actual_coverage`,
`provenance_mismatch`, and `source_insufficient`. Any other reason fails closed.

The exact downstream consumer command is in the Final Run section. It must
verify both root hashes before reading rows and must reject any row absent from
`entries[]`.

## DejaVu A1 Database Contract

### Inputs and authority

The only A1 inputs are:

```text
/private/tmp/opscat-dejavu-A1/A1/metrics.csv
/private/tmp/opscat-dejavu-A1/A1/faults.csv
/private/tmp/opscat-dejavu-A1/A1/graph.yml
```

`metrics.csv` has exact columns `name,timestamp,value,metric_type`.
`faults.csv` has exact columns
`timestamp,object,fault_description,kpi,name,node_type,root_cause_node`.
`graph.yml` is topology metadata only. A schema mismatch makes the source
unsupported.

Public rows select only metrics where:

- `name` is `<service_id>##<metric_name>`;
- `service_id` is exactly `db_003` or `db_007`;
- `metric_name` is exactly `Proc_User_Used_Pct`, `Proc_Used_Pct`, or
  `Sess_Connect`;
- `timestamp` is an integer Unix second;
- `value` parses as a finite decimal; and
- `metric_type` equals the selected metric suffix.

No other A1 metric is a database-family proxy. Public service identity is the
prefix before `##`. `graph.yml` must confirm that the service has a `DB
Session` node binding the same three metrics. It may not provide labels.

Private truth includes only fault rows satisfying all of:

```text
object == "db"
fault_description == "db connection limit"
kpi == "Proc_User_Used_Pct;Proc_Used_Pct;Sess_Connect"
name in {"db_003", "db_007"}
node_type == "DB Session"
root_cause_node == "<name> Session"
```

All comparisons are byte-exact after trimming surrounding ASCII whitespace;
case-folding or fuzzy matching is forbidden. All other A1 faults count as no
database truth and cannot become negatives for another family.

The license record is `CC-BY-4.0` with URL
`https://creativecommons.org/licenses/by/4.0/`, citation text `DejaVu A1 local
dataset snapshot: metrics.csv, faults.csv, graph.yml`, redistribution status
`derived-redacted-only`, and an explicit reviewer decision before counting.

### Windows, partitions, and labels

P105-025 owns this immutable program:

```text
window_width_seconds = 1800
stride_seconds = 300
forecast_horizon_seconds = 7200
expected_sample_period_seconds = 60
minimum_complete_triple_samples = 24 of 31
continuity_gap_limit_seconds = 120
partition_salt = "dejavu-a1-service-split-v1"
```

A public source window ends on a Unix timestamp divisible by 300, spans
`[end-1800,end]`, stays within one continuity interval, and has at least 24
timestamps where all three selected KPIs exist. Duplicate `(name,timestamp)`
records, non-finite values, or cross-service joins make the window unevaluable.
The public feature packet contains per-KPI ordered values, missingness bitmap,
count, minimum, maximum, mean, last value, and linear slope; it contains no
fault row, label, incident ID, floor value, or post-window metric.

Before opening `faults.csv`, compute
`sha256("dejavu-a1-service-split-v1:" + service_id)`. A first byte below `0x80`
maps to `held_out_test`; otherwise it maps to `real_derived_shadow`. The frozen
hashes are:

```text
db_003 45b932965cd0dca686bd5f911f7c53086bad4033c5df3323207e99452c5c75ee held_out_test
db_007 f8455be6448f2535f998e962d2dd04e08dd4a6061c535eea14a6baea3582e804 real_derived_shadow
```

No alternate salt, retry, rebucketing, or label-aware split is allowed. The
private label join then marks a window positive only when a same-service
eligible fault satisfies `0 < fault_timestamp - window_end <= 7200`. A window
cannot bind to more than one incident; ambiguity is unevaluable.

Incident identity is exact:

```text
incident_id = "dejavu-a1-db-connection-limit-<service_id>-<fault_timestamp>"
incident_group_id = incident_id
source_window_id = sha256(source_key, service_id, window_start, window_end,
                          ordered selected metric record hashes)
```

The seven eligible facts and expected eligible positive-window counts are:

| Fault timestamp | Service | Partition | Incident group | Eligible positive windows |
| ---: | --- | --- | --- | ---: |
| 1586542500 | db_007 | real-derived | `...-db_007-1586542500` | 22 |
| 1590165600 | db_003 | held-out | `...-db_003-1590165600` | 3 |
| 1590430140 | db_007 | real-derived | `...-db_007-1590430140` | 14 |
| 1590515580 | db_003 | held-out | `...-db_003-1590515580` | 17 |
| 1590519180 | db_007 | real-derived | `...-db_007-1590519180` | 18 |
| 1590689460 | db_003 | held-out | `...-db_003-1590689460` | 7 |
| 1590868020 | db_003 | held-out | `...-db_003-1590868020` | 23 |

The adapter must reproduce the unchanged incident-group floors
deterministically from the reviewed bytes: four distinct held-out groups and
three distinct real-derived groups, with 50 and 54 eligible positive windows
respectively. It may not encode those counts as labels or generate rows to
match them. If the implementation cannot reproduce the seven-fault mapping and
the 4+3 group floors from the reviewed bytes, database remains
`source_insufficient` until an additional independently reviewed honest
database source or isolated database harness is approved; it must not clone,
split, retime, or multiply any of the seven A1 incidents.

### Actual A1 coverage and insufficiency

Raw continuity is built only from timestamps where all three selected KPIs are
present, split whenever the gap exceeds 120 seconds. Evaluable coverage trims
the first 1,800 seconds of each continuity interval and drops intervals shorter
than 1,800 seconds. The exact expected evaluable interval artifacts are:

```text
db_003 held_out_test:
[1586536200,1586555040] [1590079260,1590081180]
[1590086040,1590086220] [1590094080,1590098340]
[1590165000,1590168900] [1590172200,1590184740]
[1590251400,1590251760] [1590254220,1590267960]
[1590340620,1590343560] [1590347820,1590353160]
[1590424200,1590425460] [1590428340,1590442440]
[1590510600,1590514860] [1590517500,1590530280]
[1590597000,1590600960] [1590605220,1590609960]
[1590612420,1590615360] [1590687660,1590696000]
[1590698460,1590701400] [1590769800,1590771720]
[1590774180,1590777120] [1590779580,1590789540]
[1590856200,1590858900] [1590861480,1590875940]
total = 151320 seconds = 1.7513888889 service-days

db_007 real_derived_shadow:
[1586536200,1586555940] [1590078600,1590081180]
[1590086040,1590086220] [1590094080,1590098340]
[1590165000,1590168900] [1590172200,1590184740]
[1590251400,1590251760] [1590254220,1590255960]
[1590258120,1590267960] [1590340620,1590343560]
[1590347820,1590354360] [1590424200,1590425460]
[1590428340,1590442440] [1590510600,1590514860]
[1590519540,1590530280] [1590597000,1590600960]
[1590605220,1590609960] [1590612420,1590615360]
[1590687660,1590689220] [1590691320,1590696000]
[1590698460,1590701400] [1590769800,1590771720]
[1590774180,1590777120] [1590779580,1590789540]
[1590856200,1590858900] [1590861480,1590875940]
total = 147780 seconds = 1.7104166667 service-days
```

A1 therefore proves the 4+3 incident-group floors but does not by itself meet
the unchanged 2.0 held-out database service-day floor. Before release
qualification, P105-028 must add another independently reviewed honest
database source or isolated database harness with at least 21,480 observed,
evaluable held-out service-seconds after interval union. That number is a
preflight deficit report, not a harness target: the added source program must
be designed and reviewed independently of floors, and its full actual coverage
is counted without truncating or padding to the deficit. If no such source is
approved, database remains `source_insufficient` and P106 stays locked. No A1
incident may be copied, split, cloned, moved, or retuned.

Exact A1 command:

```bash
SOURCE_DATE_EPOCH=1710000000 \
uv run --no-sync --extra dev python scripts/materialize_p105_dejavu_a1_reviewed_local.py \
  --metrics-csv /private/tmp/opscat-dejavu-A1/A1/metrics.csv \
  --faults-csv /private/tmp/opscat-dejavu-A1/A1/faults.csv \
  --graph-yml /private/tmp/opscat-dejavu-A1/A1/graph.yml \
  --output-dir /tmp/opscat-p105-reviewed-dejavu-a1 \
  --window-seconds 1800 \
  --stride-seconds 300 \
  --forecast-horizon-seconds 7200 \
  --minimum-complete-triple-samples 24 \
  --continuity-gap-limit-seconds 120 \
  --partition-salt dejavu-a1-service-split-v1 \
  --license-name CC-BY-4.0 \
  --license-url https://creativecommons.org/licenses/by/4.0/ \
  --created-at 2024-03-09T16:00:00Z \
  --review-status reviewed-local \
  --expect-incident-groups held_out_test=4,real_derived_shadow=3 \
  --expect-source-hashes
```

Outputs are
`p105-dejavu-a1-reviewed-local-manifest.json`,
`p105-dejavu-a1-public-windows.jsonl`,
`p105-dejavu-a1-pre-label-partitions.json`,
`p105-dejavu-a1-private-label-ledger.json`,
`p105-dejavu-a1-coverage.json`, and
`p105-dejavu-a1-provenance-hashes.json` under the output directory.

## Apache, Hadoop, and Zookeeper Parser Authority

P105-025 must implement actual format parsers. Each parser emits parser name
and version, source byte hash, byte/line offsets, parsed timestamp, severity or
event code, component, redacted message template, parse status, and public
event hash. Parse failure is `unsupported_family`. Parse success is still
unsupported unless a separately reviewed deploy/config-regression predicate
binds the parsed window, source offsets, and private incident ledger. The
predicate may not use file name, ordinal, partition, floor deficit, score,
post-incident values, or labels when producing public rows.

## Queue Harness Contract

P105-026 owns one component choice: RabbitMQ
`rabbitmq:3.13-management-alpine`, run only by
`tools/p105/queue/docker-compose.yml` on a private Docker network with no host
port publication. The actual image ID and RepoDigest are captured in the
registry; a changed digest requires review. The harness uses Docker CLI plus
container-local `rabbitmqadmin`; it adds no Python or application runtime
dependency.

Topology is fixed: direct exchange `p105.events`, work queues
`p105.heldout.work` and `p105.shadow.work`, dead-letter exchange `p105.dlx`, and
queues `p105.heldout.dlq` and `p105.shadow.dlq`. Work queues dead-letter rejected
messages with routing key `dead`.

Program `p105.queue.rabbitmq.v1` is immutable:

```text
seed = 105026
SOURCE_DATE_EPOCH = 1710000400
ticks = 900
tick_seconds = 1 real monotonic second
producer_rate = 20 valid messages per queue per tick
normal_consumer_rate = 20 acknowledgements per queue per tick
recovery_consumer_rate = 40 acknowledgements per queue per tick until depth 0
heldout pause = ticks 120..179 inclusive
shadow pause = ticks 240..299 inclusive
heldout poison = 5 invalid-schema messages at tick 420
shadow poison = 5 invalid-schema messages at tick 600
```

Each tick executes publish, consume/reject, then broker observation after all
commands return. Consumer rate is zero during its pause. Invalid-schema
messages are consumed and rejected with `requeue=false`; the broker, not the
harness, routes them to DLQ. The schedule never reads release floors and is not
extended or repeated to fill a deficit.

Sampling is a full census of successful public broker observations: one row per
queue per tick, with no downsampling, replay, extension, or floor-aware tuning.
Partition is assigned before reading the injection schedule:
`p105.heldout.* -> held_out_test` and
`p105.shadow.* -> real_derived_shadow`. Public messages contain deterministic
`message_id`, queue key, producer tick, and payload hash. Private injection IDs
and expected pause/DLQ outcomes are absent from public telemetry.

Public telemetry is one canonical JSONL row per queue per tick:

```text
schema_version, program_version, seed, tick, event_time,
source_window_id, service, partition_id, queue_name,
messages_ready, messages_unacknowledged, messages_total,
published_count, acknowledged_count, rejected_count, dlq_messages_ready,
ack_lag_p50_ticks, ack_lag_p95_ticks, ack_lag_max_ticks,
oldest_unacked_age_ticks, broker_image_id, broker_repo_digest,
broker_observation_sha256
```

Lag is measured from the producer tick embedded in each actually acknowledged
message to its actual acknowledgement tick. Backlog and DLQ values come from
RabbitMQ observation, not expected schedule constants.

The private ledger
`p105-queue-private-injection-ledger.json` contains `injection_id`, `seed`,
`schedule_sha256`, `queue_name`, `partition_id`, `injection_type`,
`start_tick`, `end_tick`, injected message IDs, expected broker transition,
observed transition tick, public source-window IDs, label join phase, and
ledger hash. It is joined after public sampling and partitioning.

Coverage for each queue is exactly the merged range of consecutive successful
broker-observation ticks. The fixed epoch is only canonical timestamp
normalization; the harness also records `clock_source=time.monotonic_ns` and
must prove `monotonic_elapsed_seconds >= last_tick-first_tick`. A missing tick
splits coverage. Thus a perfect run contributes at most 899 actual seconds per
queue, never four days. Output paths are:

```text
/tmp/opscat-p105-queue-harness/p105-queue-public-telemetry.jsonl
/tmp/opscat-p105-queue-harness/p105-queue-private-injection-ledger.json
/tmp/opscat-p105-queue-harness/p105-queue-pre-label-partitions.json
/tmp/opscat-p105-queue-harness/p105-queue-coverage.json
/tmp/opscat-p105-queue-harness/p105-queue-harness-manifest.json
/tmp/opscat-p105-queue-harness/p105-queue-provenance-hashes.json
```

Exact command:

```bash
SOURCE_DATE_EPOCH=1710000400 \
uv run --no-sync --extra dev python scripts/run_p105_queue_harness.py \
  --compose-file tools/p105/queue/docker-compose.yml \
  --rabbitmq-image rabbitmq:3.13-management-alpine \
  --seed 105026 \
  --ticks 900 \
  --tick-seconds 1 \
  --output-dir /tmp/opscat-p105-queue-harness \
  --mode isolated-local \
  --created-at 2024-03-09T16:06:40Z \
  --expect-no-host-ports \
  --expect-no-production-authority
```

Run twice into `/tmp/opscat-p105-queue-harness-rerun`; all six canonical files
must be byte-identical. The verifier separately changes one telemetry byte,
one ledger byte, one schedule argument, and the image digest; each change must
fail provenance verification. The harness stops and tears down the private
network on any command failure, missing observation, digest mismatch,
credential lookup, non-loopback/non-Docker endpoint, or host port publication.

## Deploy Harness Contract

P105-027 owns a standard-library-only loopback harness using two
`ThreadingHTTPServer` instances inside one local process. It imports no OpsCat
production adapter, cloud SDK, deploy client, credential provider, or PR API.

Program `p105.deploy.canary.v1` is immutable:

```text
seed = 105027
SOURCE_DATE_EPOCH = 1710001400
ticks = 1200
tick_seconds = 1 real monotonic second
requests_per_tick = 10
baseline cohort = request slots 0..7 (80%)
canary cohort = request slots 8..9 (20%)
healthy version = config-v1, 5 ms intentional service time, HTTP 200
fault injection tick = 300
faulted canary = config-v2-bad, 80 ms intentional service time,
                 every fourth canary request returns HTTP 503
```

Request IDs are `p105-deploy-<tick>-<slot>`; cohort assignment occurs before
the private fault ledger is loaded. Sampling is a full census of all completed
request observations; there is no downsampling, traffic extension, threshold
retuning, or floor-aware rerun. Partition assignment occurs before loading the
private ledger by computing
`sha256("p105.deploy.partition.v1:" + request_id)`: first byte below `0x80`
maps to `held_out_test`, otherwise to `real_derived_shadow`. Traffic order is
baseline slots then canary slots within each tick. Client latency is measured with
`time.monotonic_ns()` and canonicalized into fixed buckets
`[0,10), [10,50), [50,100), [100,250), [250,+inf)` milliseconds so equivalent
runs remain byte-identical without replacing measurement with configured
delay.

The rollback evaluator runs every 20 canary responses over the latest 100
canary responses. A breach is `error_rate >= 0.20` or measured
`p95_latency_bucket_lower_ms >= 50`. Three consecutive breaching evaluations
trigger rollback. With the fixed program, the oracle requires trigger at tick
369, local config replacement before tick 370, and the first tick-370 canary
response to carry the healthy version hash and HTTP 200. Any different result
is retained as failed evidence; the harness may not rerun with changed traffic
or thresholds.

Public telemetry rows contain:

```text
schema_version, program_version, seed, tick, request_id, event_time,
source_window_id, partition_id, cohort, public_version_hash,
status_code, latency_bucket_ms, request_count, error_count,
rolling_error_rate, rolling_latency_bucket_counts, rollback_state,
authority_counters, telemetry_row_sha256
```

The private ledger
`p105-deploy-private-injection-ledger.json` contains injection ID, seed,
schedule hash, injected config bytes/hash, injection tick, affected cohort,
expected error predicate, expected latency class, label join phase, and bound
public source-window IDs.

Rollback evidence
`p105-deploy-rollback-evidence.json` contains rule version, each 100-response
window hash, error-rate numerator/denominator, latency bucket counts, breach
booleans, consecutive breach count, trigger tick, rollback command hash,
pre/post config hashes, rollback-observed tick, first healthy request ID,
oracle expected values, oracle result, and artifact hash. Rollback is an
in-process local config swap only and grants no P106/P107 authority.

Coverage is the union of consecutive ticks with all ten measured responses and
a complete public telemetry row. It records `clock_source=time.monotonic_ns` and
is bounded by real monotonic elapsed time; a perfect run contributes at most
1,199 seconds. Missing requests split or remove coverage. Outputs are:

```text
/tmp/opscat-p105-deploy-harness/p105-deploy-public-telemetry.jsonl
/tmp/opscat-p105-deploy-harness/p105-deploy-private-injection-ledger.json
/tmp/opscat-p105-deploy-harness/p105-deploy-pre-label-partitions.json
/tmp/opscat-p105-deploy-harness/p105-deploy-rollback-evidence.json
/tmp/opscat-p105-deploy-harness/p105-deploy-coverage.json
/tmp/opscat-p105-deploy-harness/p105-deploy-harness-manifest.json
/tmp/opscat-p105-deploy-harness/p105-deploy-provenance-hashes.json
```

Exact command:

```bash
SOURCE_DATE_EPOCH=1710001400 \
uv run --no-sync --extra dev python scripts/run_p105_deploy_canary_harness.py \
  --host 127.0.0.1 \
  --seed 105027 \
  --ticks 1200 \
  --tick-seconds 1 \
  --requests-per-tick 10 \
  --fault-tick 300 \
  --output-dir /tmp/opscat-p105-deploy-harness \
  --mode isolated-local \
  --created-at 2024-03-09T16:23:20Z \
  --expect-rollback-trigger-tick 369 \
  --expect-rollback-observed-tick 370 \
  --expect-no-production-authority
```

Run twice into `/tmp/opscat-p105-deploy-harness-rerun`; all seven canonical
files must be byte-identical. Tampering with telemetry, private ledger, config
hash, rollback window, command argument, or authority counter must fail closed.

## Reproducibility and Hash Binding

Canonical JSON uses UTF-8, LF, sorted object keys, arrays in declared order,
no insignificant whitespace, finite decimal numbers only, and one trailing
newline. JSONL applies the same rule per line. `created_at` must equal the
command's explicit value and `SOURCE_DATE_EPOCH`; wall-clock time is not
serialized. Every manifest records ordered `command_argv`,
`command_argv_sha256`, source hashes, public artifact hashes, private-ledger
hash, partition hash, coverage hash, registry hash, eligibility hash, and a
root provenance hash.

Fixed epoch normalization never grants coverage. Queue and deploy coverage is
valid only when their monotonic elapsed-time attestation passes and each
covered tick has an actual broker/request observation.

## Final Run and Verification

P105-028 consumes the reviewed registry and eligibility artifacts exactly:

```bash
SOURCE_DATE_EPOCH=1710002000 \
uv run --no-sync --extra dev python scripts/materialize_p105_release_evidence.py \
  --p32-replay evals/telemetry/replay/p32_replay_pack.json \
  --p41-sources evals/real_datasets/raw/p41_sources.json \
  --p44-reviewed-local-manifest /tmp/opscat-p105-reviewed-p44/p44-reviewed-local-manifest.json \
  --p44-mode reviewed-local \
  --dejavu-a1-reviewed-local-manifest /tmp/opscat-p105-reviewed-dejavu-a1/p105-dejavu-a1-reviewed-local-manifest.json \
  --queue-harness-manifest /tmp/opscat-p105-queue-harness/p105-queue-harness-manifest.json \
  --deploy-harness-manifest /tmp/opscat-p105-deploy-harness/p105-deploy-harness-manifest.json \
  --source-registry /tmp/opscat-p105-source-expansion/p105-reviewed-source-registry.json \
  --source-eligibility /tmp/opscat-p105-source-expansion/p105-source-eligibility-manifest.json \
  --output-dir /tmp/opscat-p105-release-qualified \
  --mode release_qualified
```

If the additional honest database source is unavailable, run the same command
with `--expect-locked`; publish the exact source-insufficiency report and do not
run an unlock benchmark.

The one macro sequence remains:

1. P105-023 records independent plan review and freezes schemas/programs.
2. P105-024 records RED contract failures.
3. P105-025 through P105-027 implement adapters and the two frozen harnesses.
4. P105-028 performs actual runs, registry production, eligibility review, and
   the release benchmark once.
5. P105-029 records independent code review and architecture review, runs the
   complete verification block, and evaluates P106 only after all evidence is
   present.

Do not split this into manifest-field, parser, assertion, or rerun micro-tickets.
Finding a contract defect returns to the owning macro ticket and then resumes
the sequence; it does not create an iterative ticket chain.

Future review artifact paths are:

```text
docs/operations/p105-g006-source-expansion-plan-review.md
docs/operations/p105-g006-source-expansion-code-review.md
docs/operations/p105-g006-source-expansion-architecture-review.md
/tmp/opscat-p105-release-qualified/p105-full-verification.json
```

P106 remains locked unless those reviews approve, all exact floors and metric
gates pass, the artifact verifier passes, and every authority counter is zero.

The complete future verification block is exact and runs with the requested UV
cache:

```bash
UV_CACHE_DIR=/private/tmp/opscat-uv-cache \
uv run --no-sync --extra dev pytest -q \
  tests/test_p105_source_registry_eligibility.py \
  tests/test_p105_source_expansion_contract.py \
  tests/test_p105_dejavu_a1_materializer.py \
  tests/test_p105_log_parser_materializers.py \
  tests/test_p105_queue_harness_materializer.py \
  tests/test_p105_deploy_harness_materializer.py \
  tests/test_p105_release_qualified_evidence_contract.py \
  tests/test_p105_release_qualified_materializer.py \
  tests/test_p105_release_qualified_artifacts.py \
  tests/test_p105_release_qualified_reproducibility.py \
  tests/test_p105_release_evidence.py \
  tests/test_failure_forecast_engine.py
```

```bash
UV_CACHE_DIR=/private/tmp/opscat-uv-cache \
uv run --no-sync --extra dev pytest -q
```

```bash
UV_CACHE_DIR=/private/tmp/opscat-uv-cache \
uv run --no-sync --extra dev python scripts/verify_p105_source_expansion_artifacts.py \
  --registry /tmp/opscat-p105-source-expansion/p105-reviewed-source-registry.json \
  --eligibility /tmp/opscat-p105-source-expansion/p105-source-eligibility-manifest.json \
  --dejavu-manifest /tmp/opscat-p105-reviewed-dejavu-a1/p105-dejavu-a1-reviewed-local-manifest.json \
  --queue-manifest /tmp/opscat-p105-queue-harness/p105-queue-harness-manifest.json \
  --queue-rerun-manifest /tmp/opscat-p105-queue-harness-rerun/p105-queue-harness-manifest.json \
  --deploy-manifest /tmp/opscat-p105-deploy-harness/p105-deploy-harness-manifest.json \
  --deploy-rerun-manifest /tmp/opscat-p105-deploy-harness-rerun/p105-deploy-harness-manifest.json \
  --release-dir /tmp/opscat-p105-release-qualified \
  --expect-byte-identical-reruns \
  --expect-tamper-fixtures-fail-closed \
  --output-json /tmp/opscat-p105-release-qualified/p105-artifact-hash-verification.json
```

```bash
UV_CACHE_DIR=/private/tmp/opscat-uv-cache \
uv run --no-sync --extra dev python scripts/run_failure_forecast_benchmark.py \
  --release-benchmark /tmp/opscat-p105-release-qualified/p105-release-qualified-rows.json \
  --output-json /tmp/opscat-p105-release-qualified/p105-release-qualified-benchmark.json
```

```bash
UV_CACHE_DIR=/private/tmp/opscat-uv-cache \
uv run --no-sync --extra dev python scripts/coverage_gate.py \
  --json-output /tmp/opscat-p105-release-qualified/p105-coverage-gate.json
```

```bash
UV_CACHE_DIR=/private/tmp/opscat-uv-cache bash scripts/verify.sh --profile docs
UV_CACHE_DIR=/private/tmp/opscat-uv-cache bash scripts/verify.sh --profile fast
UV_CACHE_DIR=/private/tmp/opscat-uv-cache bash scripts/verify.sh --profile full
```

## Stop Conditions

Stop and keep `release_qualified=false` and `p106_unlocked=false` on any schema
deviation, unreviewed license/privacy decision, hash mismatch, unsupported row
counting, family heuristic, label leakage, post-label partition, changed salt,
changed harness schedule, changed threshold, floor-aware tuning, cloned
incident, duplicated window, synthetic coverage, accelerated-clock coverage,
missing actual observation, non-byte-identical canonical rerun, tamper
acceptance, production endpoint, credential read, host port, cloud/deploy API,
real PR, production mutation, self-review, failed verification, or honest
source insufficiency.
