# P122-004: security threat model, secret scanning, SBOM, licenses, and supply chain

## Goal

Build the open-source security and supply-chain release gate for the P122
local/sample release scope.

## Contract

- Refresh threat model for local demo, packaging, plugins/connectors,
  policy/action packs, frozen eval artifacts, CI, release artifacts, and
  contributor workflows.
- Define security policy, responsible disclosure, and accepted-risk process.
- Run secret scanning for repo-visible files and generated release artifacts.
- Run dependency vulnerability scanning with no unresolved high/critical
  findings.
- Run static checks for authority bypasses, unsafe defaults, command execution
  paths, deserialization, path traversal, secret logging, and external calls.
- Generate SBOM from the exact release artifact state.
- Generate license inventory and block incompatible or unknown licenses.
- Pin dependencies, containers, actions, scripts, and release tooling.
- Record checksums, provenance, and signatures/attestations where supported.

## Acceptance

Threat model, security policy, responsible disclosure, secret scan, static
scan, dependency scan, SBOM, license inventory, supply-chain pinning,
checksums, and provenance/signature checks are documented and run in CI. No
unresolved high/critical vulnerability, secret, incompatible license, unknown
license, unpinned release input, or mutation-capable default reaches release.
Accepted low/medium findings have owner, rationale, mitigation, and review
date.

## Stop Rules

Stop if security review is self-reviewed, if high/critical findings remain, if
secrets appear in repo or artifacts, if licenses are unknown or incompatible,
if release inputs are unpinned, if production-like targets appear, if
credential paths are hidden, if command execution can run as an incident
action, or if security evidence cannot be traced to exact artifact state.
