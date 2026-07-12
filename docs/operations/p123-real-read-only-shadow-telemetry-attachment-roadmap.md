# P123 Real Read-Only Shadow Telemetry Attachment Roadmap / PRD

## Objective

P123 plans a real read-only shadow telemetry attachment phase for OpsCat. It
defines how future implementation can attach to real telemetry exports,
captured snapshots, and recorded replay streams without credentials, without
live connector proof, and without mutation authority.

P123 is documentation-only and implementation is pending. It creates no source
work, test work, runtime access, credential requirement, live connector
permission, staging access, production access, deployment permission, or
mutation path by itself.

## Product Claim

P123 may claim a planned capability for read-only shadow attachment against
real telemetry artifacts and recorded replay data after future implementation
and verification pass.

P123 may not claim live production attachment, credentialed access, real-time
production proof, production-safe autonomy, staging or production mutation,
auth completion, operator replacement, or remediation authority.

Required limitation statement:

```text
P123 qualifies only a planned read-only shadow telemetry attachment path for
real exported artifacts and recorded replay. It requires no credentials and
does not prove live production operation. Auth is deferred, staging and
production mutation are disabled, and all credential, live-call, and mutation
authority counters remain exactly zero.
```

## Source Context

- P119-P121 supply local/mock/sandbox incident response, cross-system
  governance, and proactive prevention evidence with exact-zero nonlocal
  authority.
- P122 supplies open-source packaging, public contracts, reproducible local
  evidence, and honest limitation language.

P123 adds only a planning boundary for consuming real telemetry records in a
read-only, offline, replayable shadow mode.

## Non-Authority Boundary

Every P123 artifact preserves these invariants:

- auth is deferred;
- credentials, secrets, credential scopes, production identity, sessions,
  RBAC, OIDC/SSO, and approval provenance are out of scope;
- production and staging mutation are forbidden;
- live connector calls and live proof claims are forbidden;
- real telemetry is accepted only as exported files, redacted snapshots, or
  recorded replay streams supplied without credentials;
- connector writes, Kubernetes/cloud/database/network mutation, online policy
  writes, shell/subprocess incident action paths, free-form action execution,
  LLM command execution, and L4+ authority are forbidden;
- local/sandbox/shadow qualification cannot be promoted as production autonomy
  proof.

Every future evidence bundle must report these counters as exactly zero:

```text
auth_context_count
credential_scope_count
secret_material_count
live_connector_call_count
connector_write_call_count
shell_execution_as_action_count
subprocess_execution_as_action_count
kubernetes_mutation_count
cloud_mutation_count
database_mutation_count
network_mutation_count
filesystem_mutation_outside_artifact_count
online_policy_write_count
staging_mutation_count
production_mutation_count
l4_plus_action_count
freeform_action_execution_count
llm_command_execution_count
authority_escape_count
live_proof_claim_count
```

## Planned Capability Surfaces

- Artifact intake contract for real telemetry exports, redaction metadata,
  provenance metadata, clocks, source labels, and hash manifests.
- Recorded replay adapter for deterministic playback without live network
  calls.
- Shadow run contract that emits observations, judgments, gaps, and replay
  receipts without remediation or write authority.
- Capability matrix that separates artifact-backed read-only evidence from
  credentialed live connector evidence.
- Claim ledger that blocks live proof language unless a future phase explicitly
  qualifies it.

## Phases

- Phase 0 - Documentation, test spec, plan review, verification handoff, and
  ticket handoff.
- Phase 1 - Read-only artifact intake and provenance contract.
- Phase 2 - Recorded replay adapter and deterministic shadow run model.
- Phase 3 - Shadow judgment output, gap reporting, and evidence receipts.
- Phase 4 - Safety counters, no-credential guardrails, and claim ledger.
- Phase 5 - Verification handoff and dependency gate for future phases.

## Tickets

1. `[planned] P123-001` - read-only telemetry artifact intake contract
2. `[planned] P123-002` - recorded replay adapter and deterministic playback
3. `[planned] P123-003` - shadow judgment outputs and evidence receipts
4. `[planned] P123-004` - no-credential guardrails and authority counters
5. `[planned] P123-005` - claim ledger, verification handoff, and dependencies

## Release Gates

- Downstream implementation may start only after all P123 planning artifacts
  and tickets exist and are accepted.
- Real telemetry inputs are file, snapshot, or recorded replay artifacts only.
- No credential, secret, live connector call, staging mutation, or production
  mutation is introduced.
- Evidence distinguishes read-only shadow replay from live production proof.
- Implementation remains pending until future source and test changes are
  explicitly authorized and verified.

## Executable Implementation Contract

P123 implementation targets are fixed as follows:

- service: `app/services/p123_shadow_attachment.py`;
- runner: `scripts/run_p123_shadow_attachment.py`;
- tests: `tests/test_p123_shadow_attachment.py`;
- verification registry: `scripts/verify.sh`, whose `p123-release` profile must
  run the named test, regenerate both promoted outputs, and validate their
  schemas, hashes, metrics, and exact-zero authority counters;
- frozen inputs: `evals/p123/input/telemetry.jsonl` and
  `evals/p123/input/manifest.json`;
- promoted outputs: `evals/p123/shadow-report.json` and
  `evals/p123/release-evidence.json`;
- schemas: `p123.telemetry_manifest.v1`, `p123.shadow_receipt.v1`, and
  `p123.release_evidence.v1`.

The promoted fixture contains at least 100 ordered records from at least three
telemetry families. Qualification requires hash and redaction metadata
validation rate `1.0`, deterministic replay rate `1.0`, dropped and duplicated
record counts `0`, evidence citation rate `1.0`, network call count `0`, and
every authority counter exactly zero. Invalid hashes, missing provenance,
secret-shaped values, remote paths, credentials, or live-proof claims must
produce `blocked_fail_closed`.

Verification commands:

```bash
uv run --no-sync --extra dev pytest -q tests/test_p123_shadow_attachment.py
uv run --no-sync --extra dev python scripts/run_p123_shadow_attachment.py \
  --manifest evals/p123/input/manifest.json \
  --output evals/p123/shadow-report.json \
  --release-evidence evals/p123/release-evidence.json
bash scripts/verify.sh --profile p123-release
```
