# G006/P105-RQ Source-Expansion Amendment Plan

Plan source: `docs/operations/p105-g006-source-expansion-amendment.md`.
Test-spec source:
`docs/operations/p105-g006-source-expansion-test-spec-amendment.md`.

## Scope

Documentation-only actual-runtime qualification amendment for G006/P105-RQ. No
production code, test code, auth path, deploy path, or production data is
changed by this planning artifact.

## Deliverables

1. Amend the source-expansion amendment and test-spec amendment.
2. Keep P105-023 through P105-029 as the only macro tickets.
3. Update P105 roadmap and ticket index so executors have one macro sequence:
   plan review -> RED contract tests -> adapters/harness -> actual runs ->
   release benchmark -> independent code and architecture review -> full
   verify -> only then P106.

## Acceptance

- Current exact P105 floors remain unchanged.
- Unsupported-family rows are non-counting.
- DejaVu A1, the additional honest database connection-pool source/harness,
  Apache/Hadoop/Zookeeper parsers, actual RabbitMQ Docker queue runtime, and
  actual loopback `ThreadingHTTPServer` deploy runtime have concrete command
  and artifact boundaries.
- `p105.database.pool.v1` is an actual dependency-free local SQLite runtime
  using `sqlite3`, `queue.Queue`, `threading.BoundedSemaphore`, real SQL
  insert/select/update operations, fixed service partitions, a fixed
  saturation/stall schedule, observed monotonic service-seconds, and no
  floor-padding target.
- Source registry production has an exact owner, schema, output paths, command,
  closed schema-adapter registry, output paths, and downstream consumer
  boundary.
- Queue and deploy harnesses have exact fixed seeds, real monotonic duration
  attestations, schedules, partition/sampling rules, output paths,
  byte-identical rerun checks, and tamper checks.
- A1 counts only seven relevant db-connection-limit incidents; if 4+3 incident
  groups cannot be reproduced from reviewed bytes, and because A1 alone does
  not satisfy the held-out database coverage floor, the plan requires another
  honest reviewed database connection-pool source or isolated harness instead
  of cloning.
- Simulated, in-memory, accelerated-clock, or schedule-only database/queue/deploy
  artifacts are RED evidence only and cannot count toward release floors,
  source diversity, service-day coverage, or P106 unlock.
- The central materializer must consume explicit registry, eligibility, A1,
  database-pool, queue, and deploy manifests, and must reject synthetic
  four-day coverage rather than preserving compatibility with it. P105-024 owns
  the RED parser/enforcement tests, P105-028 owns CLI/parser/enforcement, and
  P105-029 owns verifier DB-pool arguments, raw attestation, tamper, and P106
  gate checks.
- Canonical artifacts and manifests exclude volatile runtime fields, raw
  attestation paths, raw attestation hashes, and any per-run volatile-derived
  value. Each run writes a verifier-owned runtime verification envelope that
  binds the canonical artifact root hash, raw attestation path/hash, and result;
  canonical rerun comparisons compare only canonical files.
- Release-counting runtime kinds are exactly `actual_sqlite_pool`,
  `actual_rabbitmq_docker`, and `actual_threading_http_server`;
  source telemetry/manifests declare only runtime attestation kind/capability.
  Only verifier-owned qualification receipts may write
  `verified_release_counting=true`, and forged source fields remain
  non-counting.
- `command_argv`, `created_at`, reviewed registry, eligibility manifest,
  provenance, privacy, license, reproducibility, and stop conditions are
  specified.
- RED-to-GREEN tests, deterministic canonicalization, two canonical reruns, and
  tamper fixtures are required before release counting.
- No synthetic padding, label leakage, post-label partitioning, heuristic
  family authority, fabricated coverage, auth change, production mutation, or
  credential reads are allowed.

## Verification

Documentation-only validation:

```bash
git diff --check
UV_CACHE_DIR=/private/tmp/opscat-uv-cache bash scripts/verify.sh --profile docs
```
