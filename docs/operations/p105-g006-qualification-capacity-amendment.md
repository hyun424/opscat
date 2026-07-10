# P105 G006 Qualification-Capacity Amendment

Status: planning only. This second amendment repairs a proven capacity defect in
the approved G006 source-expansion program. It changes no release floor, scoring
formula, auth boundary, production authority, or action-execution boundary.

## Why another amendment is required

Independent arithmetic against the implemented coverage union shows that the
currently approved exact programs cannot reach `release_qualified=true`, even
when every run is valid:

| Family | Held-out maximum | Real-derived maximum |
| --- | ---: | ---: |
| database | 180,120s (2.084722 service-days) | 176,580s (2.043750 service-days) |
| queue | 899s (0.010405 service-days) | 899s (0.010405 service-days) |
| deploy | 1,199s (0.013877 service-days) | 1,200s (0.013889 service-days) |

The honest cross-family total is 360,897 seconds, or 4.177049 service-days. More
importantly, the implemented `minimum_union_service_days` gate requires 7.0
union service-days for every supported family, despite the historical docs
calling it global. Database is also below that implemented per-family gate.
Queue additionally lacks three held-out and
two real-derived incident groups. Deploy's current private ledger does not bind
labels to public source-window IDs, so it contributes no positive/group credit.
Reruns are reproducibility evidence and never additional coverage.

The deficient baseline runs remain required: they prove the deficit with real
runtime evidence and must produce a locked, non-release-qualified receipt.

## Unchanged safety and evidence contract

- Keep all P105 row, positive, incident-group, coverage, diversity, calibration,
  useful-lead-time, false-alert, parity, provenance, and authority floors exactly
  unchanged.
- Use actual RabbitMQ Docker and loopback `ThreadingHTTPServer` observations.
- Assign service partitions before loading any private incident schedule.
- Join labels only through exact public source-window IDs after sampling and
  partitioning.
- Derive coverage only from unioned observed monotonic intervals per service.
- Count neither reruns, cloned incidents, accelerated clocks, fixed duration
  constants, padded intervals, fabricated rows, nor unsupported P44 mappings.
- Read no credentials and add no auth, production mutation, action planning, or
  action execution.
- A failed or partial run remains locked; it is never repaired by changing the
  release floor or editing observed evidence.

## Conventional capacity profile

The capacity defect motivates a larger program, but the selected shape is not
arithmetically fitted to the deficits. It uses a conventional power-of-two fleet
and one-hour soak, with a material margin above the unchanged floors. The profile
is frozen here before any new scorer result is read:

```text
profile: p105.actual-fleet-soak.256x1h.v1
logical services per family: 256
held-out services: svc-000..svc-127
real-derived services: svc-128..svc-255
requested wall-clock duration: 3,600 seconds
observation cadence: 5 seconds
scheduled samples per service: 720 (offsets 0..3,595)
partitions: fixed by service ID before private schedule loading
```

With all 720 samples observed, there are 719 adjacent five-second intervals per
service. The theoretical upper bound is therefore 3,595 seconds per service,
460,160 seconds (5.325926 service-days) per split and family, and 920,320
seconds (10.651852 service-days) per family across both splits. This is above
the unchanged implemented 7.0-day per-family union gate without relying on the
legacy programs.
Actual receipt-verified union coverage, never requested duration or this upper
bound, is the only value the scorer may use. Losing enough samples to miss a
floor keeps the run locked.

### Measured coverage contract

Every raw observation stores a verifier-only `time.monotonic_ns()` value and a
canonical sample ordinal/source-window ID. A counting adjacent interval requires:

- same source, family, split, service, run, and consecutive sample ordinal;
- strictly increasing raw monotonic time with delta from 4.0 through 7.5 seconds;
- both endpoint rows and the raw attestation bound by the runtime receipt; and
- no duplicate endpoint or interval ID.

Consecutive valid intervals form a segment. Its canonical conservative duration
is `min((sample_count - 1) * 5, floor(raw_elapsed_seconds / 5) * 5)`; invalid or
missing adjacency splits the segment and contributes no gap time. Canonical
coverage stores endpoint source-window IDs, sample counts, and this conservative
duration, never raw nanoseconds. The verifier recomputes it from the raw
attestation. P105-032 must change central materialization so fleet credit is read
only from these receipt-bound coverage segments; the existing
`created_at + tick_seconds` row-derived path remains legacy/non-fleet and cannot
grant fleet coverage.

## Frozen incident schedule

Database, queue, and deploy service IDs are respectively
`p105.fleet.database.000..255`, `p105.fleet.queue.000..255`, and
`p105.fleet.deploy.000..255`. IDs 000..127 are held-out and 128..255 are
real-derived. For each family and split, group `g00..g07` affects exactly four
disjoint services: base `0` or `128`, then offsets `4*g..4*g+3`. Services
032..127 and 160..255 are unaffected controls.

| Family | Group start | Private failure | Positive precursor range | Lead range |
| --- | ---: | ---: | ---: | ---: |
| database | `300 + 30*g` | `3300 + 30*g` | start through start + 300s | 45..50m |
| queue | `900 + 30*g` | `3300 + 30*g` | start through start + 300s | 35..40m |
| deploy | `1500 + 30*g` | `3300 + 30*g` | start through start + 300s | 25..30m |

For `g00..g07`, kind index is `g mod 4`. Database kinds are pool saturation,
slow transaction, lock contention, and checkout timeout. Queue kinds are
consumer slowdown, consumer pause, poison dead-letter, and bounded producer
burst. Deploy kinds are canary error regression, latency regression,
configuration mismatch, and bounded rollback delay. Each public precursor
perturbation lasts only through the table's 300-second positive range, after
which the service returns to control behavior. A separate actual-runtime failure
probe at the private failure timestamp confirms the delayed outcome and recovers
within 60 seconds.
Exact incident IDs are `p105-fleet-<family>-<split>-gNN`. Groups are independent
when IDs, affected services, runtime shard/queue/path, injection records, and
public source windows are all distinct. Temporal overlap is allowed only because
those runtime resources and services are disjoint.

Only affected-service public windows in the table's 300-second precursor range
are positive. Their lead times fit the unchanged family forecast intervals:
database 45..120 minutes, queue 30..90 minutes, and deploy 20..80 minutes.
Later and control windows are negative unless another reviewed incident applies.
The private ledger is generated after public rows exist and lists every exact
bound source-window ID; arithmetic ranges or inferred IDs are forbidden.

Distinct precursor windows from one incident are distinct positive rows under
the unchanged scorer. Deduplication is keyed by source-window/row identity for
positive counts and by `incident_group_id` for group counts; it must not collapse
legitimate distinct precursor rows or multiply one duplicated row/group.

## Database fleet program

Extend the isolated SQLite pool harness with a separate closed fleet adapter:

- exactly 64 independent SQLite shard files and bounded pools, four services per
  shard, pool size three, for at most 192 live SQLite connections;
- one real insert/select/update heartbeat transaction per service every 30
  seconds, at most 40,000 SQL transaction cycles, 64 worker threads, 1 GiB
  process memory, 512 MiB SQLite files/WAL, and 256 MiB output artifacts;
- each affected four-service group owns one shard, while all 192 controls use
  separate non-incident shards;
- pool saturation, slow transaction, lock contention, and checkout-timeout
  injections use actual checked-out connections, SQL, locks, and bounded
  acquisition timeouts only during the frozen precursor range, followed by an
  actual failure probe at the private failure timestamp;
- exceeding a bound, missing SQL operation counters, telemetry loss, SQLite
  corruption, or incomplete connection/file cleanup locks all fleet evidence.

## Queue fleet program

Extend the isolated RabbitMQ harness with a separate closed fleet adapter:

- exactly 256 queues plus 256 dead-letter queues in one isolated run container;
- one heartbeat message per service every 30 seconds; producer-burst incidents
  use five messages instead of one for affected services; poison incidents add
  exactly two invalid messages per affected service;
- no more than 35,872 published and 35,872 consumed/rejected messages, 512
  queues, eight concurrent management operations, 80,000 management HTTP calls,
  1 GiB container memory, 512 MiB broker disk, or 256 MiB output artifacts;
- one bulk broker-state observation for all queues at each five-second sample;
- the exact frozen eight-group schedule and 96 unaffected controls per split;
- private injection ledger entries must bind incident group, service ID, exact
  injection interval, and all affected public source-window IDs;
- cleanup is restricted to the isolated Docker project/container/volume created
  by the run; exceeding any bound or losing broker health/telemetry stops the run
  and makes all fleet evidence non-counting.

## Deploy fleet program

Extend the loopback deploy harness with a separate closed fleet adapter:

- exactly one logical service path per declared service on an actual loopback
  `ThreadingHTTPServer`;
- exactly one request per service at each sample (184,320 maximum), with observed status, latency,
  version, canary cohort, rollback state, and configuration fingerprint;
- at most 64 concurrent client/handler operations, 64 live sockets, two-second
  request timeout, 1 KiB response body, 512 MiB process memory, and 256 MiB
  output artifacts;
- the exact frozen eight-group schedule and 96 unaffected controls per split;
- private ledger entries must bind every incident to exact public
  source-window IDs after those windows are sampled and partitioned;
- no external host, production endpoint, deployment API, or mutation adapter.

The handler and client are semaphore-bounded to 64. A timeout, thread/socket
bound breach, non-loopback address, telemetry gap, or incomplete server shutdown
locks the run and grants zero fleet credit.

## Closed schema and adapter binding

Fleet evidence does not reuse the legacy small-profile schema or adapter:

```text
p105.queue.fleet_harness.v1
  -> adapter key queue_fleet
  -> p105.adapter.rabbitmq-fleet-harness.v1
p105.deploy.fleet_harness.v1
  -> adapter key deploy_fleet
  -> p105.adapter.threading-http-deploy-fleet-harness.v1
```

The database binding is:

```text
p105.database.fleet_harness.v1
  -> adapter key database_fleet
  -> p105.adapter.sqlite-pool-fleet-harness.v1
```

The registry's closed adapter set, known-root-schema set, runtime-kind map,
receipt canonical roots, CLI, source manifest, and preflight gain explicit
`database_fleet`, `queue_fleet`, and `deploy_fleet` entries. Legacy `db_pool`,
`queue`, and `deploy` adapters
must reject fleet roots, and fleet adapters must reject legacy roots or a
profile/hash other than `p105.actual-fleet-soak.256x1h.v1`. Central
materialization accepts them only through new `--database-fleet-manifest`,
`--queue-fleet-manifest`, and `--deploy-fleet-manifest` arguments plus a
verifier-owned receipt that binds the exact canonical root and raw attestation.

## Capacity and label preflight

Before either one-hour run starts, a label-blind preflight validates only the
frozen public program shape:

- 256 unique service IDs and a 128/128 fixed partition per family;
- 3,600-second requested runtime and five-second cadence;
- canonical profile/hash and expected actual runtime kind;
- the exact schedule, schema/adapter version, resource maxima, and isolated
  cleanup boundary stated above;
- no labels, scorer floors, floor deficits, or release result in public config.

A separate private review validates schedule integrity without exposing it to
the public materializer. It validates the exact table above, disjoint cohorts,
precursor/failure timestamps, and source-window binding rules, but may not
inspect or target scorer output.

## Tickets and sequence

P105-030 through P105-034 are a single ordered repair sequence:

1. P105-030 records this arithmetic defect and obtains independent plan review.
2. P105-031 adds RED contract tests for fleet shape, partition-before-label,
   exact label binding, honest coverage, resource bounds, and duplicate-credit
   rejection.
3. P105-032 implements the reviewed database/queue/deploy fleet profiles and registry
   adapters without altering legacy exact profiles.
4. P105-033 executes two runs per profile, proves canonical reproducibility,
   produces runtime qualification receipts, materializes central evidence, and
   runs the release benchmark.
5. P105-034 performs independent code and architecture review plus targeted,
   fast, docs, coverage, static, tamper, and release-gate verification.

P105-031 cannot start before an independent critic records `APPROVE`. P106 stays
locked unless P105-034 proves the exact gate payload has both
`release_qualified=true` and `p106_unlocked=true`.

## Stop conditions

Stop with P106 locked if any of the following occurs:

- observed coverage or incident groups remain below an unchanged floor;
- a service identity, interval, positive, or group is duplicated for credit;
- public evidence contains private schedule or answer-key material;
- canonical reruns differ or raw attestations fail envelope verification;
- the actual runtime kind, source registry, eligibility manifest, review ledger,
  or release receipt is missing or hash-inconsistent;
- resource bounds, isolation, cleanup, or no-production-authority checks fail;
- independent plan, code, or architecture review is not approved.
