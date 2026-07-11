# Security Threat Model

## Scope

This P122 gate covers the local/sample open-source release path: source files
visible in the repository, locked Python dependencies, local demo defaults,
plugins/connectors, policy/action packs, frozen evaluation artifacts, CI
configuration, and generated release evidence.

The release scope is local and non-production. Production mutation,
credentialed live connector execution, and operator-replacement claims remain
out of scope.

## Primary Threats

- Secret exposure through source, fixtures, generated reports, logs, or release
  artifacts.
- Mutable defaults that point at production-like, staging-like, cloud,
  Kubernetes, database, or nonlocal targets.
- Shell or subprocess execution becoming reachable from incident action,
  remediation, rollback, runbook, approval, or worker paths.
- Dependency drift, missing hashes, untraceable release artifacts, and stale
  SBOM or license evidence.
- Unknown or incompatible dependency licenses entering the release.
- Security review evidence that cannot be traced to the exact repository and
  lockfile state.

## Gate Controls

`scripts/run_p122_security_gate.py` runs without network access. It scans
repo-visible text for likely secrets and records only rule IDs, locations, and
fingerprints. It statically checks non-fixture Python/config source for
production-like mutable defaults and incident-action shell/subprocess paths.
It builds CycloneDX-shaped SBOM and license inventory artifacts from `uv.lock`.

Blocking conditions are critical/high findings, likely secrets, unknown or
incompatible licenses, and shell/subprocess incident action paths.

## Accepted Limitations

- The deterministic static gate does not query a database. The separate
  freshness-bound `pip-audit==2.10.1` release gate queries the PyPI
  vulnerability service against a hash-pinned export of `uv.lock`; that
  point-in-time result must be refreshed for every release.
- Secret detection is regex and entropy based; novel token formats can be
  missed and fixture strings can require review.
- Static authority checks are heuristic and focus on Python subprocess and
  production-like defaults in source/config, not full dataflow analysis.
- License detection prefers installed package metadata and then a documented
  deterministic allowlist in the gate script.

## Review Requirements

Any accepted low/medium finding must record owner, rationale, mitigation, and a
review date before release. High or critical findings are not accepted for P122.
