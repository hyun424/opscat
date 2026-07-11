# P122 Open-Source Production Packaging Roadmap / PRD

## Objective

P122 plans the open-source production-packaging phase for OpsCat. It packages
the verified local/mock/sandbox system from P119-P121 as an installable,
inspectable, reproducible incident-response agent with stable public
contracts, secure defaults, contributor paths, release artifacts, and
independent review.

P122 is documentation-only at this stage. It creates no runtime authority,
source-code work, test work, release artifact, production access, deployment
permission, credential scope, connector authority, or mutation path by itself.

## Product Claim

P122 may claim production-grade packaging practices, clean local install and
demo readiness, documented architecture and public extension contracts,
reproducible frozen local qualification evidence, security and supply-chain
due diligence, local/sample deployment observability, and explicit upgrade,
migration, compatibility, and release processes.

P122 may not claim production-safe autonomous remediation, production-safe
proactive prevention, live production mutation, credentialed execution, auth
coverage, operator replacement, or proven production autonomy.

Required public limitation statement:

```text
OpsCat's open-source release is qualified for local, fixture, mock, sandbox,
and reproducible evaluation workflows. It is packaged with production-grade
engineering practices, but it has not proven autonomous production operation.
Auth is deferred, production mutations are disabled, and nonlocal authority is
exactly zero unless a future environment-specific qualification phase changes
that contract.
```

## Source Context

- P119 supplies the closed-loop local/mock/sandbox incident spine, including
  diagnosis, local execution, validation/rollback, learning, war-room audit,
  crash recovery, frozen evaluation, and exact-zero nonlocal authority.
- P120 supplies source governance, read-only connector contracts, ontology
  mapping, OOD detection, calibration, frozen first-score evaluation,
  per-system metrics, and independent review.
- P121 supplies local/mock/sandbox proactive prevention with leading
  indicators, forecast horizons, evidence-before-action, false-positive and
  fatigue controls, validation/rollback, temporal/system holdouts, and
  exact-zero production authority.

P122 converts those boundaries into public release contracts and reproducible
release evidence. It does not expand authority.

## Non-Authority Boundary

Every P122 artifact preserves these invariants:

- auth is deferred;
- users, sessions, RBAC, OIDC/SSO, production identity, credentials, secrets,
  credential scopes, and production approval provenance are out of scope;
- default install and demo require no secrets;
- production and staging mutation are forbidden;
- live production and staging connectors are forbidden;
- connector writes, Kubernetes/cloud/database/network mutation, online policy
  writes, shell/subprocess incident action paths, free-form action execution,
  LLM command execution, and L4+ authority are forbidden;
- local/mock/sandbox qualification cannot be promoted as production autonomy
  proof;
- packaging quality, CI passing, or local qualification is not production
  safety evidence.

Every release evidence bundle must report these counters, and all must be
exactly zero:

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

## Public Contract Surfaces

P122 must identify and stabilize these public contracts before release:

- CLI commands, flags, exit codes, output formats, and JSON schemas.
- Supported Python package import paths versus internal-only modules.
- Configuration schema, defaults, environment variables, and local-only demo
  settings.
- Connector/plugin SDK interfaces, read-only behavior, mutation-denied
  behavior, fixture connector examples, and compatibility policy.
- Policy/action pack schemas, signatures, provenance, authority levels,
  validation probes, rollback probes, and revocation behavior.
- Incident, evidence, approval, validation, rollback, learning, replay, and
  release-evidence event schemas.
- Frozen eval input/output schema, manifest schema, hash/provenance model,
  benchmark/model-card format, and failure-report format.
- Observability contracts for metrics, logs, timeline spans, audit records,
  health checks, and diagnostics.

No contract is stable unless docs, tests, compatibility policy, and release
evidence reference it.

## Packaging, Install, and Demo

P122 must define a clean-machine path:

```text
clone -> verify prerequisites -> install -> run local demo -> inspect replay ->
run frozen eval smoke -> inspect release evidence
```

Required properties:

- supported OS/Python/container versions are declared;
- direct and transitive dependencies are pinned by locks or constraints;
- package metadata includes name, version, license, classifiers, console
  scripts, optional extras, and reproducible artifact instructions;
- container/sample deployment is local-only and has no production endpoint
  defaults;
- demo data is fixture/mock only, hash-bound, and secret-free;
- demo fails closed on production-like target names, credentials, secrets, or
  staging/production configuration;
- artifact verification covers source archive, wheel/sdist or equivalent,
  container digest where used, SBOM, license inventory, checksums,
  signatures/provenance where supported, and frozen eval hashes.

## Documentation and Tutorials

P122 must refresh public docs for README, quickstart, install, architecture,
public contracts, sample deployment, local demo, tutorials, runbooks,
troubleshooting, FAQ, limitations, upgrade/migration, compatibility,
contributor guide, release notes, benchmark/model cards, and release evidence.

Every public claim must link to frozen evidence, a test, or an explicit
limitation. Docs must not hide credential requirements, production targets,
mutation-enabled defaults, or unsupported autonomy claims.

## Security, SBOM, Licenses, and Supply Chain

The release security package must include refreshed threat model, security
policy, responsible disclosure, secret scanning, dependency vulnerability
scanning, static authority/security checks, SBOM, license inventory,
supply-chain pinning, checksums, provenance/signatures where supported, and a
risk register for accepted low/medium findings.

Release is blocked by unresolved high/critical vulnerabilities, secrets,
incompatible or unknown licenses, unpinned release inputs, mutation-capable
defaults, hidden production targets, or self-reviewed security gates.

## CI, Evals, Performance, and Observability

CI must cover supported OS/Python/container modes, tests, contract checks,
authority-boundary checks, packaging build/install/uninstall, local
container/sample deployment smoke, docs checks, frozen eval reproducibility,
release-evidence consistency, security scans, secret scans, SBOM, license
checks, dependency pinning, static authority scans, and artifact
reproducibility.

Performance and soak evidence must report install time, cold-start time, demo
startup/completion time, event throughput, replay throughput, incident/audit
record durability under crash/restart, CPU/memory/storage envelope, local soak
duration, zero lost incident/audit/replay records, and exact-zero authority
counters.

Agent observability must expose health/readiness, structured logs with
correlation IDs, metrics, timeline spans or trace-like records, audit/replay
inspection, diagnostics, redaction guarantees, no secret logging, and
operator-visible fail-closed reasons.

## Upgrade, Migration, Compatibility, and Release Artifacts

P122 must define semantic versioning or an equivalent compatibility policy,
upgrade paths, config migrations, local state migration rules, rollback
behavior, frozen eval artifact compatibility, connector/plugin SDK
compatibility, policy/action pack compatibility and revocation, backup/restore,
disaster recovery, and release notes.

Release artifacts must include source archive, package artifacts, container
recipe/digest where applicable, SBOM, license inventory, checksums,
provenance/signatures where supported, release notes, migration guide,
benchmark/model cards, release evidence, and the limitations statement.

## Phases

- Phase 0 - Documentation, test spec, plan review, verification handoff, and
  ticket handoff.
- Phase 1 - Architecture cleanup and stable public contracts.
- Phase 2 - Packaging, clean install, sample deployment, and local demo.
- Phase 3 - Public docs, tutorials, contributor guide, and limitations.
- Phase 4 - Security threat model, secret scanning, SBOM, licenses, and
  supply chain.
- Phase 5 - CI matrix and reproducible frozen evals.
- Phase 6 - Performance, soak, crash/replay, and agent observability.
- Phase 7 - Upgrade, migration, compatibility, and release artifacts.
- Phase 8 - Release candidate review, verification handoff, and public
  limitations.

## Tickets

1. `[planned] P122-001` - architecture cleanup and stable public contracts
2. `[planned] P122-002` - packaging, clean install, sample deployment, and local demo
3. `[planned] P122-003` - public docs, tutorials, contributor guide, and limitations
4. `[planned] P122-004` - security threat model, secret scanning, SBOM, licenses, and supply chain
5. `[planned] P122-005` - CI matrix and reproducible frozen evals
6. `[planned] P122-006` - performance, soak, crash/replay, and agent observability
7. `[planned] P122-007` - upgrade, migration, compatibility, and release artifacts
8. `[planned] P122-008` - release candidate review, verification handoff, and public limitations

## Release Gates

- Downstream implementation may start only after roadmap, test spec, plan
  review, verification handoff, ticket README, and P122-001 through P122-008
  exist and are accepted.
- Public claims distinguish production-grade packaging and local qualification
  from unproven production autonomy.
- Auth remains deferred, production mutations are prohibited, and exact-zero
  nonlocal authority counters are preserved.
- Architecture and public contracts are versioned, documented, tested, and
  compatibility-scoped.
- Clean install, local sample deployment, one-command demo, package artifact
  verification, and uninstall checks pass in the declared matrix.
- Docs contain no hidden credential, production target, mutation default, or
  unsupported autonomy claim.
- Security scans, SBOM, license checks, supply-chain checks, checksums, and
  provenance/signature checks pass with no unresolved high/critical findings.
- Frozen local evals are reproducible from pinned manifests and every release
  claim traces to evidence or a limitation.
- Performance/soak proves zero lost incident/audit/replay records for the
  promoted local qualification scope.
- Independent review blocks self-review, untraced claims, nonzero authority
  counters, hidden production targets, auth claims, and production mutation
  paths.
