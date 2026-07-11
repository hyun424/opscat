# P122 Adversarial Test Specification

This specification is a planning handoff for future P122 implementation. It
does not require source-code edits, test edits, runtime access, connector
access, credentials, release publication, or production mutation during this
documentation turn.

## Contract and Authority

- Reject auth context, credentials, secrets, production target strings,
  staging target strings, live connector names, connector write fields,
  Kubernetes/cloud/database/network mutation fields, online policy writes,
  shell/subprocess action fields, free-form action prose, LLM command text,
  and L4+ action requests.
- Require exact-zero counters for every authority dimension listed in the
  P122 roadmap.
- Reject any default install, demo, CI, tutorial, fixture, screenshot, release
  note, or evidence bundle that implies production mutation, credentialed
  execution, auth completion, operator replacement, or production autonomy.
- Reject release claims that treat packaging quality, CI passing, or local
  qualification as proof of production safety.

## Architecture and Public Contracts

- Detect undocumented public APIs, advertised internal modules, breaking schema
  changes, unstable CLI output, missing exit-code contract, missing JSON
  schema, missing owner module, missing version, missing stability level,
  missing deprecation path, missing backward-compatibility rule, missing
  authority level, missing docs ref, missing test ref, and missing release
  evidence ref.
- Reject public contracts that allow nonlocal authority or fail to state
  `nonlocal_authority_allowed=false`.
- Require contract tests to fail on undocumented breaking changes or authority
  expansion.

## Packaging, Install, and Artifact Verification

- Detect clean-machine install failure, unsupported matrix drift, missing
  prerequisites, missing extras, bad package metadata, broken console script,
  uninstall leftovers, unpinned dependency, transitive dependency drift,
  unreproducible artifact, checksum mismatch, missing source archive,
  missing wheel/sdist or equivalent, container digest mismatch, missing
  provenance/signature status, and stale artifact verification.
- Require install, uninstall, package build, metadata inspection, dependency
  lock validation, checksum validation, and artifact verification for the
  declared matrix.

## Demo and Sample Deployment

- Reject secret requirement, production-like target, staging-like target,
  nonlocal network call, hidden live connector, hidden mutation path,
  missing replay evidence, missing authority counters, nonzero authority
  counter, local sample deployment with production endpoint defaults, fixture
  data without hashes, and demo output that implies production autonomy.
- Require the one-command local demo to use fixture/mock/local sandbox data,
  fail closed on production-like configuration, record replay artifacts, and
  expose exact-zero authority counters.

## Documentation, Tutorials, and Contributor Paths

- Detect untraced claim, production-autonomy implication, missing limitation
  link, stale command, untested command, broken link, hidden credential
  requirement, mutation-enabled default, missing setup path, missing test path,
  unclear review process, unclear security process, contract change without
  evidence, and docs/test mismatch.
- Require README, quickstart, install, tutorials, architecture, public
  contracts, local demo, sample deployment, runbooks, troubleshooting, FAQ,
  limitations, upgrade/migration, compatibility, contributor guide, release
  notes, benchmark/model cards, and release evidence to use bounded claim
  language.

## Security

- Detect secret in repo or artifact, high/critical vulnerability, unsafe
  deserialization, path traversal, command execution as action, secret
  logging, external call bypass, mutation-capable connector default,
  production-like target, stale threat model, missing disclosure process,
  accepted risk without owner, accepted risk without mitigation, and
  self-reviewed security gate.
- Require refreshed threat model, security policy, responsible disclosure,
  secret scan, dependency vulnerability scan, static authority/security scan,
  and documented risk register for accepted low/medium findings.

## SBOM, Licenses, and Supply Chain

- Detect missing SBOM component, unknown license, incompatible license,
  missing license inventory, unpinned dependency, unpinned action, unpinned
  container, unpinned release tooling, missing provenance, missing checksum,
  signature mismatch, checksum mismatch, SBOM generated from stale state, and
  artifact that cannot be traced to source and dependency state.
- Require SBOM, license inventory, dependency/container/action/tooling pinning,
  checksums, and provenance/signature status for the release artifact set.

## CI and Frozen Eval Reproducibility

- Detect unsupported matrix drift, skipped required gate, stale cache producing
  release evidence, partial eval promoted, flaky gate ignored, missing frozen
  manifest, hash tampering, consumed holdout reuse, nondeterministic score,
  aggregate-only metric, missing denominator, missing confidence interval,
  self-reviewed evidence, stale evidence hash, and release claim without
  evidence ref.
- Require CI to run tests, authority-boundary checks, packaging checks, docs
  checks, security scans, secret scans, SBOM/license checks, dependency
  pinning checks, frozen eval reproducibility, and release-evidence
  consistency.

## Performance, Soak, Crash/Replay, and Observability

- Detect lost incident record, lost audit record, lost replay record, lost
  timeline span, lost authority rejection, memory leak, storage leak, restart
  data loss, crash during report write, missing denominator, missing hardware
  context, aggregate-only performance claim, missing health status, missing
  authority rejection signal, secret in logs, uncorrelated timeline, replay not
  inspectable, and fail-closed reason hidden from operators.
- Crash before and after install, demo startup, incident ingest, evidence
  request, decision, approval, validation, rollback, replay write, eval write,
  release-evidence write, and report write.
- Require promoted soak to report zero lost incident, audit, timeline, replay,
  and authority records in local/sample scope.

## Upgrade, Migration, Compatibility, and Release Artifacts

- Detect irreversible migration without backup, silent config rewrite,
  unsupported old artifact accepted, supported artifact rejected, plugin SDK
  break, policy/action pack break, schema break, eval artifact break, local
  state migration drift, rollback failure, missing deprecation notice, missing
  compatibility policy, missing release notes, missing migration guide, and
  artifact verification that cannot run from a clean checkout.
- Require migrations either to succeed deterministically or fail closed with
  actionable messages.

## Release Review and Public Claims

- Reject self-review, missing independent reviewer, untraced public claim,
  unresolved critical finding, unresolved high finding, nonzero authority
  counter, hidden production target, hidden credential path, auth completion
  claim, production mutation claim, live connector authority claim,
  operator-replacement claim, aggregate-only evidence, and packaging quality
  as production proof.
- Require independent verification distinct from planner and implementer.

## Named RED Cases

- `auth_context_present`, `credential_scope_present`,
  `secret_material_present`, `live_connector_call_present`,
  `connector_write_present`, `production_target_present`,
  `staging_target_present`, `kubernetes_mutation_present`,
  `cloud_mutation_present`, `database_mutation_present`,
  `network_mutation_present`, `online_policy_write_present`,
  `shell_action_present`, `subprocess_action_present`,
  `freeform_action_execution_present`, `llm_command_execution_present`,
  `l4_plus_action_present`, and `authority_escape_present`.
- `undocumented_public_api`, `advertised_internal_module`,
  `breaking_schema_without_policy`, `unstable_cli_output`,
  `missing_deprecation_path`, `authority_level_mismatch`,
  `missing_contract_test_ref`, and `missing_release_evidence_ref`.
- `clean_install_failure`, `bad_package_metadata`, `broken_console_script`,
  `uninstall_leftovers`, `unpinned_dependency`, `unreproducible_artifact`,
  `checksum_mismatch`, `missing_provenance`, and `container_digest_mismatch`.
- `demo_requires_secret`, `demo_production_like_target`,
  `demo_nonlocal_network_call`, `demo_hidden_mutation_path`,
  `demo_missing_replay_evidence`, and `demo_nonzero_authority_counter`.
- `untraced_doc_claim`, `production_autonomy_implication`,
  `missing_limitations_link`, `stale_doc_command`, `broken_doc_link`,
  `hidden_credential_requirement`, and `mutation_enabled_default`.
- `secret_in_artifact`, `high_vulnerability_unresolved`,
  `critical_vulnerability_unresolved`, `unsafe_deserialization`,
  `path_traversal`, `command_execution_as_action`,
  `secret_logging`, `external_call_bypass`, and `self_reviewed_security_gate`.
- `missing_sbom_component`, `unknown_license`, `incompatible_license`,
  `unpinned_action`, `unpinned_container`, `unpinned_release_tooling`,
  `stale_sbom`, and `signature_mismatch`.
- `skipped_ci_gate`, `stale_cache_release_evidence`,
  `partial_eval_promoted`, `flaky_gate_ignored`, `missing_frozen_manifest`,
  `hash_tampering`, `consumed_holdout_reuse`, `nondeterministic_score`,
  `aggregate_only_metric`, and `self_reviewed_evidence`.
- `lost_incident_record`, `lost_audit_record`, `lost_replay_record`,
  `restart_data_loss`, `memory_leak`, `storage_leak`,
  `crash_report_write_loss`, `missing_authority_rejection_signal`,
  `secret_in_logs`, and `replay_not_inspectable`.
- `irreversible_migration_without_backup`, `silent_config_rewrite`,
  `unsupported_old_artifact_accepted`, `plugin_sdk_break`,
  `rollback_failure`, `missing_compatibility_policy`,
  and `clean_checkout_artifact_verification_failure`.
- `self_review`, `missing_independent_review`, `unresolved_critical_finding`,
  `unresolved_high_finding`, `production_readiness_claim`,
  `operator_replacement_claim`, `auth_completion_claim`,
  `packaging_as_production_proof`, and `unproven_autonomy_claim`.

## Verification Profile

Future implementation must provide targeted P122 verification for public
contracts, packaging, clean install, local demo, documentation, contributor
paths, security, SBOM, licenses, supply chain, CI, frozen eval
reproducibility, performance, soak, crash/replay, observability,
upgrade/migration, compatibility, release artifacts, independent review,
honest public claims, and exact-zero authority counters. Documentation
completion does not require those tests to exist yet.
