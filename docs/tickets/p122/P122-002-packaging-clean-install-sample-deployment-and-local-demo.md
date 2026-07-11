# P122-002: packaging, clean install, sample deployment, and local demo

## Goal

Create a clean-machine install path, package artifacts, local sample
deployment, and one-command fixture/mock/local sandbox demo with replay
evidence and exact-zero authority counters.

## Contract

- Declare supported OS, Python, and container versions.
- Pin direct and transitive runtime, test, docs, release, and tooling
  dependencies with locks or constraints.
- Define package metadata, version, license, classifiers, console scripts,
  optional extras, reproducible build instructions, source archive, wheel/sdist
  or equivalent artifacts, checksums, and provenance/signature status where
  supported.
- Provide local-only sample deployment with no production endpoint defaults.
- Provide one-command demo using fixture/mock/local sandbox data that requires
  no secrets, fails closed on production-like config, records replay artifacts,
  and reports exact-zero authority counters.
- Verify install, uninstall, artifact checksums, container digest where used,
  SBOM/license references, and frozen eval hashes.

## Acceptance

Declared clean-machine install and demo matrix passes at 1.0 success. Demo
requires no secrets, uses only fixture/mock/local sandbox targets, fails closed
on production-like config, records replay evidence, and reports exact-zero
authority counters. Package metadata, locks/constraints, checksums, artifact
verification, and uninstall behavior are validated.

## Stop Rules

Stop if install or demo requires credentials, reaches production/staging, calls
live connectors, performs nonlocal network calls outside allowed artifact
checks, mutates production-like targets, hides mutation paths, omits replay
evidence, has nonzero authority counters, leaves uninstall residue in claimed
paths, uses unpinned release inputs, or markets clean install as production
autonomy.
