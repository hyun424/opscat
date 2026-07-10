# P105 G006 Source-Expansion Amendment

Status: planning only. This amendment extends the approved P105 release-qualified
evidence plan without changing any existing P105 floor, metric threshold, P106
gate row, or safety authority boundary.

## Goal

Expand G006/P105-RQ source coverage with actual reviewed local sources for
database, queue, and deploy families while preserving the current release
contract:

- unsupported-family rows are non-counting;
- actual Apache, Hadoop, and Zookeeper parsers replace heuristic family
  authority;
- actual coverage only, with no fabricated four-day coverage or broad constant
  intervals;
- every manifest binds `command_argv`, `created_at`, provenance hashes, reviewer
  status, license, privacy, and eligibility;
- DejaVu A1 at `/private/tmp/opscat-dejavu-A1/A1` is the local reviewed source
  candidate for database connection-limit ground truth;
- queue and deploy evidence come only from isolated local harnesses with private
  injection ledgers and no production mutation;
- P106 remains locked until plan review, RED tests, adapters/harnesses, actual
  runs, release benchmark, independent code and architecture review, and full
  verification all pass in that order.

## Non-Negotiable Carry-Forwards

This amendment does not relax the existing release-hardening floors:

- held-out per supported family:
  `evaluated_window_count >= 30`,
  `non_abstained_evaluated_forecast_count >= 24`,
  `actual_positive_count >= 6`,
  `incident_group_count >= 4`, and
  `covered_service_seconds / 86400 >= 2.0`;
- real-derived per supported family:
  `evaluated_window_count >= 20`,
  `non_abstained_evaluated_forecast_count >= 16`,
  `actual_positive_count >= 4`,
  `incident_group_count >= 3`, and
  `covered_service_seconds / 86400 >= 1.0`;
- `distinct_source_record_sets >= 3`;
- no canonical source tuple contributes more than `0.60` of a supported
  family's release-qualified real-derived rows;
- global `total_covered_service_seconds / 86400 >= 7.0`.

If actual reviewed sources do not meet those exact floors, the accepted result
is a locked source-insufficiency artifact. The implementation must not add
synthetic padding, copy records, infer labels from floor deficits, leak labels
into public rows, assign partitions after labels, or count unsupported-family
rows.

## Reviewed Source Registry and Eligibility Manifest

G006 must add two first-class artifacts before any materializer can score rows:

- `p105-reviewed-source-registry.json`
- `p105-source-eligibility-manifest.json`

The registry records every candidate source, including P32/P41/P44, DejaVu A1,
queue harness output, and deploy harness output. Each source entry must include
`source_key`, `source_family_candidate`, `source_system`, `source_dataset`,
`local_path`, `source_content_hash`, `license_name`, `license_url`,
`citation_text`, `redistribution_status`, `privacy_review_status`,
`reviewer_id`, `reviewed_at`, `command_argv`, `created_at`, and
`provenance_hash`.

The eligibility manifest is the only authority that may declare whether a row
can count for a supported family. It must be produced before scoring and before
private label joins. It includes:

- `eligible_for_release_floor`;
- `family_authority_source`;
- `unsupported_family_reason`;
- `coverage_interval_authority`;
- `label_ledger_ref`;
- `partition_manifest_hash`;
- `privacy_license_registry_hash`;
- `source_parser_version`;
- `source_adapter_version`;
- `command_argv`;
- `created_at`.

Heuristic family authority is forbidden. Family assignment can count only when
the reviewed registry and eligibility manifest name an approved parser or
harness source with explicit family mapping. Any unknown, ambiguous, unmapped,
or parser-failed source is `unsupported_family` and contributes zero rows,
positives, incident groups, source diversity, and coverage to supported-family
floors.

## Source Programs

### Database: DejaVu A1

The local DejaVu A1 source is already available at:

```text
/private/tmp/opscat-dejavu-A1/A1/metrics.csv
/private/tmp/opscat-dejavu-A1/A1/faults.csv
/private/tmp/opscat-dejavu-A1/A1/graph.yml
```

The source is a database candidate only for explicitly reviewed `db connection
limit` faults. The plan records the supplied license as CC-BY-4.0; the future
registry must still include the exact citation text, license URL, reviewer, and
redistribution status before rows can count. `faults.csv` is private label
ledger input, not a public feature source. `metrics.csv` and `graph.yml`
produce public features, source windows, coverage intervals, and topology
metadata before labels join.

Required command:

```bash
uv run --no-sync --extra dev python scripts/materialize_p105_dejavu_a1_reviewed_local.py \
  --metrics-csv /private/tmp/opscat-dejavu-A1/A1/metrics.csv \
  --faults-csv /private/tmp/opscat-dejavu-A1/A1/faults.csv \
  --graph-yml /private/tmp/opscat-dejavu-A1/A1/graph.yml \
  --license-name CC-BY-4.0 \
  --output-dir /tmp/opscat-p105-reviewed-dejavu-a1 \
  --review-status reviewed-local \
  --expect-source-hashes
```

The materializer must use actual timestamps from A1 records for coverage.
Coverage may not be rounded up to days, padded to four days, inferred from row
count, or copied from a top-level constant. If the timestamp span provides less
coverage than the floor requires, the run remains locked.

### Deploy: Apache, Hadoop, and Zookeeper Parsers

The amendment requires actual parsers for Apache, Hadoop, and Zookeeper log
formats before those rows can be eligible. Parser output must include source
line offsets, parsed timestamp, severity or event code when available, parser
version, parse status, and a redacted public event payload. Family authority is
limited to reviewed deploy/config-regression predicates over parsed windows.

Rows from Apache, Hadoop, or Zookeeper parser failures are
`unsupported_family`. Rows from parser successes with no reviewed deploy/config
predicate are also `unsupported_family`. Parser family assignment must not use
record ordinal, partition bucket, release floor deficit, private label,
post-incident values, or source filename.

### Queue: Isolated Local RabbitMQ or Kafka Harness

Queue evidence must come from an isolated local harness that emits real
consumer lag, backlog, and dead-letter telemetry plus a private injection
ledger. The preferred approach is the lightest repo-compatible harness:
standard-library local process and file/socket simulation if it can produce
real queue metrics; otherwise a local Docker Compose RabbitMQ or Kafka service
is allowed only for this harness and only when no new app dependency is added.

Required telemetry:

- consumer lag or offset delay;
- queue depth or backlog;
- dead-letter count;
- producer and consumer timestamps;
- private injected event IDs and fault windows;
- no production broker endpoint;
- no credential read;
- no external network requirement.

The harness must write a private injection ledger that joins only after
label-blind partitioning. Harness-produced public telemetry and private injected
labels must be hash-bound in the eligibility manifest.

### Deploy: Isolated Local Canary/Config Regression Harness

Deploy evidence must come from an isolated local canary/config regression
harness with measurable error rate, latency, and rollback signal. It must not
control production deploy tooling, call a cloud API, read credentials, open a
real pull request, or mutate production.

Required telemetry:

- baseline and canary cohorts;
- config or version change event;
- request count;
- error rate;
- latency distribution;
- rollback trigger and rollback-observed timestamp;
- private injection ledger;
- no production authority counter.

Rollback in this harness is local-only and evidentiary. It proves deploy-family
forecast labels and coverage; it does not grant P106, P107, or production
execution authority.

## Coverage, Partitions, and Labels

Coverage must come from actual source timestamps, parsed event timestamps,
harness telemetry timestamps, or reviewed timestamp bounds. The implementation
must remove any fabricated four-day coverage claim or equivalent constant
coverage shortcut. Coverage artifacts must publish raw intervals and merged
intervals for each `split_id`/`family`/`service`/`source_system` scope.

Partitioning happens before private labels join. Partition assignment inputs are
source identity, timestamp or deterministic sequence, source family candidate,
and versioned salt. They do not include private labels, incident IDs, label
positivity, P24/P105 score, floor deficit, useful lead time, false-alert status,
or gate outcome.

The private ledgers for DejaVu A1, queue harness, and deploy harness must record
label join phase, label source, label hash, incident group, source-window ID,
materialized-record hash, pre-label partition ID, and unevaluable reason.

## Privacy, License, and Reproducibility

All source-expansion runs must be local/offline by default. Raw public or
temporary input sources are not committed. Committable artifacts are reviewed,
redacted, derived, hash-bound manifests and small fixture outputs only.

Every artifact must include `command_argv`, `created_at`, source hashes,
materialized hashes, registry hash, eligibility hash, privacy/license hash,
private ledger hash or hash-safe reference, and benchmark hash. Two runs over
the same inputs must be byte-identical except for explicitly allowed output
directory paths; if paths are included in hashes, the command must normalize
them.

## Macro Sequence

G006 source expansion is one macro sequence:

1. Plan review approves this amendment and records review scope.
2. RED contract tests fail for the missing registry, eligibility, parsers,
   DejaVu A1 adapter, queue harness, deploy harness, coverage, and provenance
   rules.
3. Adapters and harnesses are implemented behind local/offline command
   boundaries.
4. Actual source runs materialize reviewed-local artifacts and locked negative
   artifacts.
5. The release benchmark runs only against eligible, reviewed, actual coverage.
6. Independent code review and independent architecture review approve the
   artifact, implementation, and source authority boundaries.
7. Full targeted, fast, docs, and coverage verification passes.
8. Only then may P105-RQ set `release_qualified=true` and evaluate whether
   `p106_unlocked=true`; otherwise P106 remains locked.

## Ticket Set

- P105-023: plan review, source registry, and eligibility contract.
- P105-024: RED contract tests for source expansion.
- P105-025: DejaVu A1 database adapter and actual log parsers.
- P105-026: isolated local queue harness.
- P105-027: isolated local deploy canary/config regression harness.
- P105-028: actual source runs and release benchmark.
- P105-029: independent code and architecture review, full verification, and
  P106 handoff gate.

These are macro tickets. Do not split them into repeated parser-only,
manifest-only, or one-assertion micro tickets unless a ticket is blocked by an
external dependency that cannot be resolved locally.

## Acceptance

The amendment is implementation-ready when:

- the reviewed source registry and eligibility manifest are mandatory before
  scoring;
- unsupported-family rows are explicitly non-counting;
- DejaVu A1 is database-only and label-private, with CC-BY-4.0 metadata
  recorded before row eligibility;
- Apache, Hadoop, and Zookeeper rows require actual parsers and reviewed
  deploy/config predicates;
- queue evidence comes from isolated local lag/backlog/dead-letter telemetry;
- deploy evidence comes from isolated local canary/config telemetry with
  rollback observation and no production authority;
- coverage uses actual intervals only;
- `command_argv`, `created_at`, provenance binding, privacy, license,
  reproducibility, and private ledgers are required artifacts;
- all existing floors and P106 gates remain unchanged;
- P106 remains locked until the complete macro sequence passes.

## Stop Conditions

Stop and keep P106 locked if any source lacks registry review, license, privacy
review, source hash, parser version, eligibility decision, private ledger,
actual coverage interval, pre-label partition, provenance binding, or
reproducible command metadata. Also stop if any row counts through heuristic
family authority, unsupported-family status, label leakage, synthetic padding,
duplicated records, fabricated coverage, production mutation, credential reads,
or nonlocal broker/deploy authority.
