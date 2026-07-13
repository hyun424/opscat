# P125 Adversarial Test Specification

This specification began as the planning handoff and is now implemented by the
P125 service, runner, tests, promoted input profile, and `p125-release`
verification profile. It still authorizes no credentials, infrastructure,
staging access, production access, or mutation.

## Contract and Authority

- Reject credentials, secrets, live connectors, production/staging targets,
  mutation fields, shell/subprocess action fields, free-form action prose, LLM
  command text, and L4+ action requests.
- Require exact-zero authority counters for every future P125 evidence bundle.
- Reject claims that local/sandbox endurance proves production SLO compliance.

## Long-Running Runs

- Detect missing duration, missing event count, missing hardware context,
  missing replay manifest, missing resource limits, stale input hashes,
  aggregate-only claims, and cherry-picked windows.
- Require promoted runs to declare scope and denominators.

## Restart and Recovery

- Detect lost event, lost observation, lost judgment, lost receipt, lost audit
  record, lost authority rejection, duplicate record, corrupt resume, partial
  write, and hidden restart failure.
- Require restart matrix evidence for clean stop, crash, partial write, report
  interruption, and replay resume.

## Cost and Degradation

- Detect unbounded CPU, memory leak, storage leak, runaway retry, unbounded
  queue growth, missing per-event cost, missing p95/p99 latency, and degraded
  judgment quality without flag.
- Require cost reports to include local resource context and failure limits.

## Named RED Cases

- `production_slo_claim`
- `missing_duration_denominator`
- `lost_replay_event`
- `lost_shadow_judgment`
- `lost_authority_counter`
- `duplicate_after_restart`
- `corrupt_resume_state`
- `memory_leak`
- `storage_leak`
- `runaway_retry`
- `nonzero_authority_counter`

## Verification Profile

`bash scripts/verify.sh --profile p125-release` provides targeted verification
for long-running manifests, restart matrix, recovery, data-loss ledgers, local
cost envelopes, degradation gates, hashes, and exact-zero authority counters.
