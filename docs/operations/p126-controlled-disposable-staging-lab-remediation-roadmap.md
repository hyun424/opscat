# P126 Controlled Disposable Staging-Lab Remediation Roadmap / PRD

## Objective

P126 plans controlled remediation only inside a disposable staging-lab
environment. It defines how future implementation can exercise remediation
flows against intentionally disposable lab resources without touching real
staging, production, credentials, or live customer systems.

P126 is documentation-only and implementation is pending. It creates no source
work, test work, lab environment, credential requirement, real staging access,
production access, or mutation path by itself.

## Product Claim

P126 may claim a planned disposable-lab remediation qualification framework
after future implementation and verification pass.

P126 may not claim real staging remediation, production remediation,
credentialed execution, auth completion, operator replacement, or
production-safe autonomous action.

Required limitation statement:

```text
P126 permits remediation planning only for controlled disposable staging-lab
resources created for test destruction. It never authorizes real staging or
production mutation. Auth is deferred, credential authority is zero, and all
real staging, production, live connector, and non-lab mutation counters remain
exactly zero.
```

## Source Context

- P123-P125 supply read-only replay, measured judgment quality, and
  long-running shadow resilience.

P126 is the first planned action-oriented phase, but action is confined to a
disposable lab and remains pending until future implementation and verification
exist.

## Non-Authority Boundary

Every P126 artifact preserves these invariants:

- auth is deferred;
- credentials, secrets, real staging identity, production identity, and
  credential scopes are out of scope;
- real staging and production mutation are forbidden;
- disposable lab resources must be created, labeled, isolated, and destroyed
  as part of test evidence;
- live customer systems, shared staging systems, and persistent infrastructure
  are out of scope;
- connector writes, cloud/database/network mutation, and shell/subprocess
  actions are permitted only if future implementation proves they are confined
  to disposable lab fixtures; otherwise they remain forbidden;
- all real staging, production, credential, live connector, and authority
  escape counters remain exactly zero.

## Lab Remediation Surfaces

- Disposable lab manifest with resource names, isolation boundary, TTL,
  owner, destruction receipt, and non-overlap proof.
- Remediation capability catalog limited to lab fixtures.
- Preflight policy that blocks unlabeled, persistent, shared, real staging, or
  production targets.
- Simulation-before-action and rollback-before-promotion gates.
- Evidence package with action receipts, validation, rollback, cleanup,
  destruction, and exact-zero non-lab counters.

## Phases

- Phase 0 - Documentation, test spec, plan review, verification handoff, and
  ticket handoff.
- Phase 1 - Disposable lab manifest and target-isolation contract.
- Phase 2 - Lab-only remediation capability catalog and preflight gate.
- Phase 3 - Simulation, execution receipts, validation, and rollback.
- Phase 4 - Cleanup, destruction proof, and non-lab authority counters.
- Phase 5 - Verification handoff and P127 dependency gate.

## Tickets

1. `[planned] P126-001` - disposable lab manifest and isolation contract
2. `[planned] P126-002` - lab-only remediation catalog and preflight gate
3. `[planned] P126-003` - simulation, execution receipts, validation, and rollback
4. `[planned] P126-004` - cleanup, destruction proof, and non-lab counters
5. `[planned] P126-005` - verification handoff and controlled-action dependencies

## Release Gates

- Downstream implementation may start only after all P126 planning artifacts
  and tickets exist and are accepted.
- Every mutable target is disposable, labeled, isolated, TTL-bound, and
  destruction-proven.
- Real staging and production mutation counters remain exactly zero.
- Claims say disposable staging-lab only, never real staging or production.
- Implementation remains pending until future source and test changes are
  explicitly authorized and verified.

## Executable Contract

For P126, “staging lab” means an ephemeral local temporary directory plus
in-memory state only. It never means a real staging cluster, account, endpoint,
database, broker, cloud resource, or credential. Catalog actions are typed
Python state transitions; shell, subprocess, network, connector-write,
Kubernetes, cloud, and database drivers are forbidden.

- Service: `app/services/p126_lab_remediation.py`
- Runner: `scripts/run_p126_lab_remediation.py`
- Tests: `tests/test_p126_lab_remediation.py`
- Verify profile: `p126-release`
- Input: `evals/p126/input/lab-scenarios.json`
- Outputs: `evals/p126/lab-report.json`, `evals/p126/release-evidence.json`
- Schemas: `p126.lab_scenario.v1`, `p126.action_receipt.v1`,
  `p126.release_evidence.v1`

At least 30 scenarios must achieve deterministic approval accuracy 1.0,
unsafe/non-lab blocking 1.0, eligible validation 1.0, rollback success 1.0,
duplicate effects 0, cleanup residue 0, and exactly-zero non-local, staging,
production, credential, and external mutation authority.

Verification commands are the targeted pytest file, the runner, and
`bash scripts/verify.sh p126-release`.
