# P122-008: release candidate review, verification handoff, and public limitations

## Goal

Run the final independent review and produce the verification handoff for an
honestly scoped open-source release candidate.

## Contract

- Maintain planning artifacts:
  `docs/operations/p122-open-source-production-packaging-roadmap.md`,
  `docs/operations/p122-test-spec.md`,
  `docs/operations/p122-plan-review.md`,
  `docs/operations/p122-verification-handoff.md`,
  `docs/tickets/p122/README.md`, and tickets P122-001 through P122-008.
- Require verification handoff to include changed-file inventory, commands run
  and exact results, release evidence manifest, artifact hashes, dependency
  locks, SBOM, license inventory, scan outputs, eval hashes, performance/soak
  results, exact authority counters, unresolved risks, accepted findings, and
  independent review result.
- Require independent review authored by a separate context from planner and
  implementer.
- Require public limitations to distinguish production-grade packaging,
  locally qualified behavior, and unproven production autonomy.
- Block release on nonzero authority counters, unresolved high/critical
  security findings, untraced claims, self-review, hidden production targets,
  auth/credential claims, or production mutation paths.

## Acceptance

Independent review covers all P122 tickets, docs, tests, CI, package
artifacts, security, SBOM/licenses, supply chain, frozen evals,
performance/soak, crash/replay, observability, upgrade/migration,
compatibility, release notes, public claims, and limitations. The verification
handoff identifies exact commands, results, artifacts, risks, owners, and
release-candidate verdict. Final public claims remain limited to
production-grade packaging practices and local/mock/sandbox qualification.

## Stop Rules

Stop if release review is self-reviewed, if verification evidence is missing
or stale, if public limitations are missing, if docs imply proven production
autonomy, if any authority counter is nonzero, if high/critical security
findings remain unresolved, if production targets or credentials are hidden in
artifacts, if aggregate-only evidence is promoted, or if release claims exceed
local qualification and production-grade packaging.
