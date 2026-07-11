# P122-001: architecture cleanup and stable public contracts

## Goal

Clarify architecture boundaries and stabilize public contracts for CLI,
package APIs, configuration, connector/plugin SDK, policy/action packs, event
schemas, observability, frozen evals, and release evidence without expanding
authority.

## Contract

- Document public versus internal modules, supported import paths, CLI
  commands, flags, exit codes, output formats, JSON schemas, config defaults,
  environment variables, and local-only demo settings.
- Define connector/plugin SDK interfaces with read-only behavior,
  mutation-denied behavior, fixture connector examples, compatibility policy,
  and versioning.
- Define policy/action pack schemas with signatures, provenance, authority
  levels, validation probes, rollback probes, revocation behavior, and
  nonlocal authority disallowed.
- Define incident, evidence, approval, validation, rollback, learning, replay,
  release-evidence, and observability event schemas.
- Require every public contract to include stability level, version, owner
  module, schema/interface ref, backward compatibility rule, deprecation rule,
  authority level, `nonlocal_authority_allowed=false`, test refs, doc refs,
  and release evidence refs.

## Acceptance

Public/internal boundaries are documented and tested. Contract tests fail on
undocumented breaking changes, unstable CLI output, missing compatibility
rules, missing deprecation rules, missing evidence refs, or authority
expansion. Existing P119-P121 authority semantics remain unchanged and
exact-zero nonlocal authority remains testable.

## Stop Rules

Stop if architecture cleanup changes runtime authority, advertises internal
modules as stable APIs, omits authority levels, permits nonlocal authority,
adds auth, credentials, live connectors, production/staging mutation, shell or
subprocess action paths, Kubernetes/cloud/database/network mutation, online
policy writes, free-form action execution, LLM command execution, L4+
authority, or public contracts without docs/tests/evidence refs.
