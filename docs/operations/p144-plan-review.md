# P144 Plan Review

## Decision

APPROVE

## Frozen Inputs

- Plan: `.omx/plans/opscat-p144-loopback-provider-adapter-conformance.md`
- Plan SHA-256: `sha256:592153aec6310429b4ddd728b25633d2553b07682513463d23641ed1fdd9e886`
- Test specification: `docs/operations/p144-test-spec.md`
- Test specification SHA-256: `sha256:7266e0546023b69b34fab6b9c548316e546f71a9001cd2be71e7caa9aa60969f`
- Independent critic agent: `019f632a-b9d5-7643-b8e9-08804917f8f2`

## Findings

- P0: 0
- P1: 0
- P2: 0
- P3: 0

The initial review reported P0: 5, P1: 3, P2: 2, and P3: 0. The
reviewed revision closes every finding by defining a non-serializable,
process-owned receiver capability; separating terminal P142 transport attempts
from P144 adapter retries; making committed requests with unknown responses
review-only and non-retryable; fixing exact schemas, bounds, canonical hashes,
64 selectors, disjoint counters, and two-phase freeze/review semantics; pinning
the exact P142/P143 dependencies and fixture response shapes; and expanding
entrypoint, runtime, source, socket, and environment guards.

## Reviewed Request-Binding Erratum

The second implementation review discovered that the original prose derived
`attempt_id` from `request_hash` while also including that attempt ID in
`fixed_headers` covered by the request self hash. That construction was
cryptographically circular. The reviewed correction defines an exact request
core, computes `request_binding_hash` from that core, derives each attempt ID
from delivery ID plus request binding hash plus attempt index, persists the
index-zero attempt header, and changes only that header on retry wire bytes.

The erratum also makes all six persisted header values canonical and rejects
every Transfer-Encoding response. It changes no authority boundary, selector
name, selector count, dependency pin, retry eligibility, crash/replay rule, or
two-phase review requirement. The superseded plan hash was
`sha256:788498c12ab2afdaf6db57258deaf85b7f34fcd2056b973e43e4157b9bbcd16f`;
the superseded test-spec hash was
`sha256:63e3c1cdc2db1b20f4cf8c42edc10216f35476d729ae862593158df8ae840e87`.
The corrected hashes in Frozen Inputs are approved for a new preliminary
freeze and independent implementation re-review.

## Approved Boundary

P144 is implementation-ready only as a provider-shaped conformance lab over an
already-bound numeric-loopback receiver owned by the current process. The
receiver capability cannot be reconstructed from configuration, CLI arguments,
environment variables, persisted artifacts, or P142 authority. It accepts only
the exact numeric addresses `127.0.0.1` and `::1`, and listener identity and
liveness must be revalidated before connection.

The milestone grants no credential, authentication, environment, DNS, proxy,
TLS, provider SDK, configurable endpoint, external socket, callback, external
delivery, P133 acknowledgement, approval, action, remediation, ticket, staging
mutation, production mutation, subprocess, arbitrary command, or
operator-replacement authority. A provider-shaped local fixture response is
evidence of contract behavior, not provider certification or external delivery.

## Residual Limitations

- Numeric-loopback provider fixtures do not certify any real provider or prove
  external delivery.
- Local process provenance is not cryptographic attestation.
- Independent reviewer identity is recorded but not externally authenticated.
- Indeterminate post-send state requires human review and never permits an
  automatic retry.
