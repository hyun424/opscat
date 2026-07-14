# P139 Plan Review

## Review identity and limitation

Review identity: `local-adversarial-p139-plan-reviewer`

Implementation identity: `p139-parent-implementation-agent`

An external Codex review was attempted in read-only mode and rejected by the
desktop security reviewer because it would transmit private local plan/source
context to an external process. The review was not bypassed. This document is a
separate local adversarial pass and does not claim authenticated third-party
reviewer identity.

## First verdict — REJECT

Findings: P0=0, P1=3, P2=3, P3=0.

### P1-1: prior P138 controls can make every later service restart stop stale

P138's `_prior_control_stop_reason` evaluates existing readiness and heartbeat
age before the new loop starts. The draft required validating those records but
did not define how a clean terminal tuple is consumed. A process restarted after
the stale interval could therefore stop before observation forever.

Required amendment: add an explicit crash-safe restart-control rollover under
the P139 service lease and P138 supervisor lease. Bind readiness, heartbeat,
termination, ledger, checkpoint, and P139 exit receipt; journal the rollover;
archive the exact tuple; descriptor-revalidate removal of only fixed readiness
and heartbeat; preserve immutable P138 termination history; forbid P138 ledger
or checkpoint mutation; test every split commit.

### P1-2: runtime validation cannot depend on repository-local tracked evals

The draft said startup validates current tracked P138/P136/P137 artifacts. An
installed wheel or container does not contain the source repository's tracked
`evals/` tree, so this would make deployment either impossible or dependent on
mutable external files.

Required amendment: source-bind exact expected dependency hashes in P139 code.
Only the release runner reads tracked artifacts and proves the constants current.
Runtime validates its bundle against the source-bound constants.

### P1-3: P138 loop time does not advance into P136 or publisher inputs

P138 computes a per-cycle `now` value but the production loop passes the same
mutable P136 runtime and publisher inputs without updating their `now` and
`created_at` fields. Long-running receipt freshness and publication metadata can
therefore remain pinned to the first fixture timestamp.

Required amendment: update those mutable input fields immediately before every
cycle, lock behavior with P138 regression tests, regenerate source-bound P138
review/evidence, and bind P139 to the new dependency hashes.

### P2-1: `ready` requires evidence that the service process is actually alive

Fresh readiness bytes alone can outlive a crashed process. Status must probe the
whole-service advisory lease without mutation and require that it is held before
returning `ready`. A free lease plus active-looking readiness is unclean/stale,
not healthy.

### P2-2: dual-lease ordering was unspecified

Restart rollover needs both P139 and P138 ownership. The plan must mandate
P139-service lease before P138-supervisor lease and prohibit the reverse order,
including recovery, to avoid deadlock and split ownership.

### P2-3: evaluator subprocess/signal activity could leak into runtime authority

The release evidence must keep evaluator process launch, SIGINT/SIGTERM/SIGKILL,
and crash injection in a separate exact schema. Runtime process/signal counters
remain zero and cannot be copied from expected values.

## Amendment audit

The approved plan now:

- defines source-bound dependency constants and release-only tracked-artifact
  reads;
- advances P138 cycle time into P136 and publisher inputs with regression and
  release-evidence regeneration;
- defines intent/history/removal/completion restart-control rollover;
- fixes lease order as service -> P138;
- requires held-lease proof for `ready`;
- rejects negative readiness/heartbeat age so future-dated controls cannot
  satisfy `ready`;
- adds stale-self-stop, rollover crash, and real clean restart coverage;
- requires final review of evaluator-vs-runtime process/signal accounting.

## Final verdict — APPROVE WITH RECORDED REVIEW LIMITATION

Findings after amendment: P0=0, P1=0, P2=0, P3=0.

Implementation may begin. Release remains blocked until an implementation
review binds the final source/matrix/manifest and records zero P0/P1/P2 findings.
