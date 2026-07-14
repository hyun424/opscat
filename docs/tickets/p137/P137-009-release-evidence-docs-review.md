# P137-009 - Release evidence, docs, and source-bound review

## Scope

Create P137 release evidence, documentation refresh, and separate review
artifacts for plan readiness and final frozen-source implementation.

## Acceptance

- Release evidence binds source hashes for P134/P135/P136/P137 validators,
  P137 runtime, runner, fixtures, docs, the P136 handoff chain root and accepted
  bundle, and the canonical matrix output.
- Plan-readiness review covers only roadmap, test spec, and tickets.
- Preliminary canonical matrix runs to a temporary directory and freezes source,
  profile, fixtures, and matrix output.
- Final frozen-source implementation review is based on the frozen source,
  current docs, frozen profile, frozen fixtures, and frozen matrix output, and
  has zero unresolved P0/P1/P2 findings.
- Documentation preserves explicit non-goals and no-auth/no-credentials/
  no-network/no-provider-API/no-notification/no-action/no-remediation authority.
- Structural release validation fails without the final implementation-review
  artifact and must consume the frozen matrix plus review without regenerating
  reviewed inputs. Any source/profile/fixture/matrix change invalidates review.
- Release status is exactly `p137_local_evidence_triage_qualified`.
