# P131 Test Specification

## Required proofs

- Scheduler-contract tests call the injected sleeper between cycles and prove
  missed deadlines do not create a tight catch-up loop.
- A bounded one-second real-time smoke proves the system clock/sleeper path;
  it is not a long-soak or 24/7 availability claim.
- Restart resumes from an atomic checkpoint and does not duplicate JSONL rows.
- Truncation/rotation is visible and duplicate hashes remain suppressed.
- Missing, stale, malformed, and hash-invalid heartbeat files fail the watchdog.
- Rehashed but structurally incomplete source checkpoints fail closed.
- Post-configuration symlink swaps cannot escape data or artifact allowlists.
- Process health and source freshness are evaluated independently.
- Synthetic canary validates serialization, signal detection, and the no-action
  policy contract. It does not claim to prove the external JSONL producer path.
- Daily reports are written atomically and contain no raw secret-bearing data.
- Direct connector configuration is rejected until a reviewed read-only
  observation-authority contract exists.
- Credential, mutation, shell, and unsupported source configuration fails closed.
- Exact P121 authority counters are present and all integer zero.
- CLI bounded mode exits; continuous mode is never used by automated tests.
- Health/readiness API responses are safe when state is absent or stale.

## Release gates

- Targeted P131 tests, Ruff, and Mypy pass.
- Restart replay observes zero lost and zero duplicated accepted records.
- Canary success rate is 1.0 for the promoted fixture.
- Watchdog detects every injected dead-man failure.
- No production, staging, credential, shell, subprocess, or action authority.
