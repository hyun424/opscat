# P175 — Deterministic Live Qualification Harness

## Goal

Turn the P174 disposable GCP lab into a reproducible qualification campaign
that can prove, rather than merely claim, safe incident response behavior.

## Deliverables

1. A capability-bound, lab-only typed fault endpoint with exactly three faults:
   `queue_backlog`, `canary_regression`, and `worker_pause`.
2. A deterministic harness that records 200 consecutive healthy observer
   windows and runs a seeded, claim-correct 100-episode typed campaign:
   25 restart recovery, 25 canary rollback, 20 rejection,
   20 rollback-required, and 10 safety-boundary scenarios.
3. Evidence-bound live validation for `restart_worker` and
   `rollback_canary`, plus reversible `tune_pool` rollback-required and real
   ProviderLab rejection/safety-boundary episodes.
4. Hash-chained machine-readable results, summary gates, and server-snapshot
   fault cleanup evidence.

## Safety Contract

- Exact P174 project, target, run, lease, and evidence bindings. Action and
  fault capabilities are mandatory, distinct authorities; the fault authority
  is sent only to `POST /faults` and `POST /faults/cleanup`.
- Live runs require `--authority-file`; raw capability CLI arguments are not
  accepted. The file must be a regular, non-symlink file with mode `0600` and
  exactly these keys: `P174_ACTION_CAPABILITY`, `P174_FAULT_CAPABILITY`,
  `P174_PROJECT_ID`, `P174_TARGET_ID`, `P174_RUN_ID`, and
  `P174_POLICY_VERSION`. The parser rejects unknown, duplicate, missing, blank,
  whitespace-padded, or unbound values. Project, target, and run must match the
  provider manifest, policy must be `p174-policy-v1`, and the two
  capabilities must be distinct and at least 32 characters.
- No arbitrary command, URL, process, container, Docker socket, or model-chosen
  target.
- No non-P174 project IDs and no production/user-staging mutation flags.
- Fail closed on stale/missing observer evidence, invalid chains, unexpected
  action application, or rollback failure.

## Acceptance Gates

- 200/200 consecutive healthy windows. Live observer requests are paced at no
  less than 15 seconds. Every accepted window must advance `evaluation.ts` by
  at least 14 seconds and strictly increase the receipt sequence tail; repeated
  or rapidly replayed windows fail closed.
- 100/100 deterministic episodes match their expected outcomes.
- `--max-scenarios` is diagnostic-only: it never lowers `required_exact=100`
  and a truncated campaign cannot qualify.
- Every episode records fault/action/expected outcome plus baseline, post, and
  cleanup state hashes with concrete state-delta proof.
- Every healthy-window evidence event records its explicit derived `window_id`,
  UTC `timestamp`, and receipt-tail `sequence` in the hash chain.
- Real backlog improvement for `restart_worker` episodes.
- `rollback_canary` restores `canary_version=stable`.
- Rejected and safety-boundary episodes execute `ProviderLab.run_action` and
  prove no protected-state mutation with real target `GET /state` snapshots.
- CLI observer traffic uses `GET /collect`; fault injection uses target
  `POST /faults`; action execution uses `ProviderLab` with
  `HttpP174ProviderTransport` and at least three post-check samples. GETs
  require HTTP 200 and mutation POSTs require HTTP 202.
- Every episode submits the workload-issued cleanup token to
  `POST /faults/cleanup`, then re-reads `GET /state` and compares the protected
  state with the real pre-fault server snapshot. Client-synthesized state is
  not qualification evidence.
- Provider and observer receipt chains validate.
- Final API, Prometheus, Loki, and host-compute evidence is healthy and bound.
- Reviewed workload teardown removes remote runtime and local authority files.

## Execution Order

1. Implement and unit-test the typed fault surface.
2. Implement and unit-test the pure deterministic campaign engine.
3. Add the IAP runner and evidence bundle writer.
4. Review the plan and code independently.
5. Deploy a reviewed bundle to the disposable P174 project.
6. Collect 200 windows, run 100 episodes, verify, and tear down.
