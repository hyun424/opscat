# P122-007: upgrade, migration, compatibility, and release artifacts

## Goal

Define upgrade, migration, compatibility, backup/restore, rollback, and
artifact verification for the P122 open-source release.

## Contract

- Define semantic versioning or equivalent compatibility policy.
- Document supported upgrade paths from previous release state to P122.
- Define config migrations, local state migrations, rollback behavior,
  backup/restore, disaster recovery, and fail-closed behavior for unsupported
  artifacts.
- Define CLI, config, schema, plugin/connector SDK, policy/action pack, frozen
  eval artifact, release-evidence, and local state compatibility rules.
- Define deprecation policy and revocation behavior.
- Assemble release artifacts: source archive, package artifacts, container
  recipe/digest where applicable, SBOM, license inventory, checksums,
  provenance/signatures where supported, release notes, migration guide,
  benchmark/model cards, release evidence, and limitations statement.
- Require independent artifact verification from a clean checkout.

## Acceptance

Supported upgrade paths migrate deterministically or fail closed with clear
messages. Compatibility rules are explicit and tested. Release artifacts are
complete, traceable to exact source/dependency state, and independently
verifiable from a clean checkout.

## Stop Rules

Stop if migration rewrites config silently, migration is irreversible without
backup, unsupported old artifacts are accepted, supported artifacts are
rejected, rollback fails, compatibility policy is missing, plugin SDK breaks
without deprecation path, release artifacts lack SBOM/license/checksum/
provenance status, or artifact verification requires hidden credentials or
production access.
