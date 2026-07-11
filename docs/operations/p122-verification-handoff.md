# P122 Verification Handoff

Schema marker: `p122.verification_handoff.v1`.

Current status: implementation evidence is executable and the independent
release-candidate verdict remains pending until a distinct reviewer records it.
The docs and migration reports are generated as
`evals/p122/docs-verification.json` (`p122.docs_verification.v1`) and
`evals/p122/migration-compatibility.json`
(`p122.migration_compatibility.v1`).

This handoff is the current evidence template and status ledger for P122
release-candidate review. It separates executed local evidence from pending or
blocked gates and does not claim production autonomy, credentialed execution,
or live production mutation.

## Scope

Verification must prove only the P122 release scope:

- production-grade open-source packaging practices;
- clean local install and local demo;
- stable public contracts;
- reproducible frozen local qualification evidence;
- security, SBOM, license, and supply-chain gates;
- CI, performance, soak, crash/replay, and observability for local/sample
  deployment;
- upgrade, migration, compatibility, release artifacts, and independent review.

Verification must not claim production-safe autonomous remediation,
production-safe proactive prevention, credentialed execution, auth completion,
operator replacement, live production mutation, or proven production autonomy.

## Required Inventory

Future executors must provide changed-file inventory grouped by:

- architecture and public contracts;
- packaging, install, sample deployment, and demo;
- docs, tutorials, contributor guide, and limitations;
- security, threat model, secret scanning, SBOM, licenses, and supply chain;
- CI and frozen eval reproducibility;
- performance, soak, crash/replay, and observability;
- upgrade, migration, compatibility, backup/restore, and rollback;
- release artifacts, release notes, benchmark/model cards, and release
  evidence.

The inventory must explicitly list files that were source, test, docs, CI,
eval, release artifact, or generated evidence changes.

## Current Executable Evidence Commands

The following commands are part of the current P122 verification surface:

```bash
uv run --no-sync --extra dev pytest tests/test_p122_public_contracts.py tests/test_p122_performance_soak.py tests/test_p122_migration_compatibility.py tests/test_p122_docs_verification.py
uv run --no-sync --extra dev python scripts/verify_p122_docs.py
uv run --no-sync --extra dev python scripts/verify_p122_docs.py --output evals/p122/docs-verification.json
uv run --no-sync --extra dev python scripts/verify_p122_migration_compatibility.py --workdir /tmp/opscat-p122-migration --output evals/p122/migration-compatibility.json
uv run --no-sync --extra dev python scripts/run_p122_performance_soak.py --iterations 1000 --workdir /tmp/opscat-p122-soak --output evals/p122/performance-soak.json
```

Status fields to fill after execution:

```json
{
  "schema_version": "p122.verification_handoff.v1",
  "commands_executed": ["targeted P122 tests", "docs verifier", "migration verifier"],
  "commands_pending": ["independent release-candidate review"],
  "blocked_gates": ["independent_review_passed"],
  "accepted_limitations": ["local fixture evidence only"]
}
```

## Required Command Evidence

Verification must include commands run and exact results for:

```text
clean install check
unit/integration/contract/authority tests
package build and artifact verification
install/uninstall verification
local sample deployment smoke
one-command local demo
docs lint/link/schema examples
secret scan
dependency vulnerability scan
static authority/security scan
SBOM generation and license check
supply-chain pinning check
frozen eval reproducibility
release evidence consistency check
performance smoke
long soak or documented long-soak command
crash/replay verification
observability and redaction checks
upgrade/migration/rollback tests
clean-checkout artifact verification
independent review checklist
```

If a command is not available, the completed handoff must state why, identify
the owner, and mark the related release gate blocked or out of claimed scope.

## Release Evidence Manifest

The release evidence manifest must include:

- source revision and artifact hashes;
- package artifact names, versions, checksums, and provenance/signature status
  where supported;
- dependency lock or constraints references;
- container recipe and digest where applicable;
- SBOM and license inventory references;
- secret scan, dependency scan, static scan, and authority scan outputs;
- frozen eval manifests, hashes, scores, denominators, confidence intervals,
  and reproducibility status;
- performance and soak reports with hardware/context and denominators;
- crash/replay receipts;
- demo replay artifacts;
- observability evidence for health, metrics, logs, timeline/replay, audit,
  diagnostics, redaction, and fail-closed reasons;
- migration, rollback, backup/restore, and compatibility reports;
- public claim traceability map;
- unresolved risks, accepted low/medium findings, owners, mitigations, and
  review dates;
- independent review result and release-candidate verdict.

## Exact-Zero Authority Counters

Every release evidence bundle must report these counters, and every value must
be exactly zero:

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
undocumented_public_claim_count
untraced_release_claim_count
```

Any nonzero value blocks release.

## Public Claim Traceability

Every README, tutorial, benchmark card, release note, portfolio statement, and
limitations statement must classify claims as one of:

- production-grade packaging practice;
- locally qualified incident-response behavior;
- locally qualified proactive prevention behavior;
- explicit limitation or unproven production-autonomy statement.

Claims about production must link to the public limitation statement. Claims
about behavior must link to frozen evidence, test evidence, or a limitation.
Untraced claims block release.

## Independent Review Requirements

Independent review must be authored by a context separate from the planner and
primary implementer. It must accept or reject:

- each P122 ticket;
- public contract stability and compatibility;
- clean install and demo evidence;
- docs/tutorials/contributor paths;
- security, SBOM, licenses, and supply-chain evidence;
- CI and frozen eval reproducibility;
- performance, soak, crash/replay, and observability;
- upgrade, migration, compatibility, and release artifacts;
- public claims and limitations;
- exact-zero authority counters.

Review must reject self-review, missing evidence, stale evidence, aggregate-only
evidence, unresolved high/critical security findings, hidden production
targets, hidden credential paths, auth claims, production mutation paths,
operator-replacement claims, and packaging-as-production-proof claims.

## Troubleshooting

- Missing command output: leave the gate pending or blocked; do not infer pass
  status from a prior JSON artifact.
- Self-review: set `distinct_reviewer = false` and block release.
- Any nonzero authority counter: block release even if all packaging checks
  pass.

## Release-Candidate Stop Conditions

Block release-candidate handoff on nonzero authority counters, unresolved
high/critical security findings, incompatible or unknown licenses, missing
SBOM, missing provenance/checksum status, unpinned release inputs, broken
clean install, broken local demo, missing replay evidence, lost incident/audit/
replay records, missing observability for authority rejection, unreproducible
frozen evals, stale release evidence, untraced public claims, hidden production
targets, hidden credential requirements, irreversible migrations without
backup, rollback failure, self-review, or any claim beyond production-grade
packaging plus local qualification.
