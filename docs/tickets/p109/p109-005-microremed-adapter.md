# P109-005 MicroRemed Result Adapter

Import externally produced MicroRemed-compatible run bundles, verify provenance
and hashes, and recompute recovery rather than trusting submitted success
flags. Require an independent verifier identity, implementation/policy hashes,
raw before/after observations, health-check spec hashes, immutable source
revision, and allowed signer binding. Actor-only or self-signed verification is
smoke-only. Do not redistribute upstream MicroRemed code while its repository
does not provide a root license.

Validate `p109.microremed_bundle.v1`, `p109.microremed_attempt.v1`, and
`p109.microremed_verifier.v1`. Require `external_execution=true`; preserve raw
evidence and action hashes, ignore submitted summary/success values, and fail
closed on an actor/verifier identity collision.
