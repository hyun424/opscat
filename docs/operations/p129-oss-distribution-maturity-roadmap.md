# P129 OSS Distribution Maturity Roadmap / PRD

## Objective

P129 plans open-source distribution maturity beyond P122 packaging:
governance, support policy, release hygiene, security intake, compatibility,
and community readiness. Implementation is pending.

## Product Claim

P129 may claim only a planned OSS maturity framework. It may not claim
production autonomy, credentialed execution, auth completion, real staging or
production mutation, or enterprise support readiness.

## Scope

- Governance, maintainership, contribution, and decision records.
- Security disclosure, vulnerability triage, and release-blocking policy.
- Versioning, compatibility, deprecation, and migration policy.
- Distribution channels, artifact provenance, license/SBOM refresh, and
  reproducible release checklist.
- Support boundaries and public limitation language.

## Non-Authority Boundary

Distribution maturity does not add runtime authority. Auth is deferred,
credentials are out of scope, production/staging mutation is forbidden, and all
authority counters remain exactly zero.

## Tickets

1. `[planned] P129-001` - governance, maintainership, and contribution policy
2. `[planned] P129-002` - security intake and release-blocking policy
3. `[planned] P129-003` - versioning, compatibility, and migration policy
4. `[planned] P129-004` - artifact provenance, SBOM, licenses, and distribution
5. `[planned] P129-005` - verification handoff and beta readiness gate

## Gates

- Implementation may start only after all P129 planning artifacts and tickets
  are accepted.
- Public distribution claims stay evidence-qualified and local/sandbox scoped.
- No support or production-readiness claim exceeds verified evidence.

## Executable Contract

- Service: `app/services/p129_distribution_maturity.py`
- Runner: `scripts/run_p129_distribution_maturity.py`
- Tests: `tests/test_p129_distribution_maturity.py`
- Verify profile: `p129-release`
- Outputs: `evals/p129/distribution-report.json`,
  `evals/p129/release-evidence.json`
- Schemas: `p129.distribution_report.v1`, `p129.release_evidence.v1`

Governed documentation includes README, SECURITY, CONTRIBUTING, installation,
compatibility, and limitations. Gates require reproducible wheel and sdist;
clean install, contract, demo, and uninstall checks; explicit stable/internal
imports; all contract references resolvable; SBOM and license completeness
1.0; high/critical vulnerabilities 0; detected secrets 0; unpinned runtime
dependencies 0; production-enabled defaults 0; and exactly-zero runtime
authority. Python 3.12 through 3.14 are declared; an unavailable interpreter
remains explicitly pending rather than passing silently.

Verification commands are the targeted pytest file, the runner, and
`bash scripts/verify.sh p129-release`.
