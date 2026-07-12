# P123-002: recorded replay adapter and deterministic playback

## Goal

Define deterministic recorded replay for real telemetry artifacts without live
network or connector dependency.

## Contract

- Replay uses immutable inputs, hash manifests, deterministic ordering, and
  stable run IDs.
- Replay emits input hashes, event counts, dropped-record counts, timing model,
  and receipt references.
- Replay rejects wall-clock-dependent, mutable, credentialed, or live-call
  execution.

## Acceptance

Repeated replay over the same artifact set produces the same receipts and
shadow observations.

## Stop Rules

Stop if replay performs live network calls, depends on hidden mutable state,
omits receipts, or is used as a live proof claim.

