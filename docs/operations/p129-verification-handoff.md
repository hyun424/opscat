# P129 Verification Handoff

Schema marker: `p129.verification_handoff.v1`.

Current status: planning complete when accepted; implementation evidence is
pending.

## Required Future Evidence

- Changed-file inventory for OSS policies, docs, release checks, tests, and
  generated reports.
- Governance and contribution policy evidence.
- Security intake and release-blocking evidence.
- Compatibility and migration policy evidence.
- Artifact provenance, SBOM, license inventory, and limitations evidence.
- Exact-zero authority counters.

## Dependencies

- Depends on P122 packaging boundaries and P128 evidence UX for public
  inspectability.
- Blocks P130 public beta if OSS maturity evidence is absent.
- Does not unblock auth, credentials, live connectors, staging, production, or
  mutation authority.

## Stop Conditions

Block handoff on hidden credentials, production-readiness claims, missing
security policy, missing SBOM/license inventory, missing provenance, unknown
licenses, self-review, or nonzero authority counters.

