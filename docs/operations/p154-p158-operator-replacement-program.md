# P154-P158 Operator Replacement Qualification Program

## Objective

This program advances OpsCat from a single-cycle read-only staging shadow into
an evidence-qualified monitoring-operator replacement candidate. The program
does not grant production mutation authority or claim that recorded fixtures are
real customer staging outcomes.

## Ordered phases

1. **P154 longitudinal shadow quality ledger**
   measures judgment agreement, false positives, abstention, citations, and
   continuity over ordered shadow sessions.
2. **P155 active evidence acquisition**
   executes bounded read-only follow-up requests and measures whether missing
   evidence is resolved without unsupported conclusions.
3. **P156 hybrid judgment arbitration**
   treats an LLM as an advisory hypothesis source and combines it with
   deterministic evidence checks. Invalid citations, unsafe actions, malformed
   responses, or unjustified overrides fail closed.
4. **P157 reversible remediation effectiveness lab**
   executes only fixed actions against process-owned disposable state, verifies
   postconditions, and closes harmful changes through rollback.
5. **P158 operator replacement readiness gate**
   binds P154-P157 evidence and states the maximum qualified operating scope,
   remaining blockers, and forbidden claims.

## Safety invariants

- P154-P156 are observation and judgment only.
- P155 follow-ups are provider-neutral read operations with fixed budgets.
- P156 model output is advisory and can never authorize an action.
- P157 actions target only `process-owned-lab://` resources and use a fixed
  capability registry. No shell, subprocess, arbitrary URL, cloud, database, or
  production adapter is accepted.
- P158 cannot report unattended production readiness unless real longitudinal
  staging evidence, production-grade identity, tenant isolation, credential
  operations, audited provider actions, and rollback evidence exist. Those
  prerequisites are intentionally absent.
- Canonical inputs are recorded qualification fixtures. Live NVIDIA or customer
  staging calls are never required by verification.
- Every artifact is canonical JSON, self-hashed, source-bound, predecessor-bound,
  and reviewed by an identity distinct from the writer.

## Release sequence

Each phase follows:

`plan -> plan review -> RED tests -> implementation -> final review -> release evidence`

The phases execute strictly in order because every release evidence file is the
next phase's predecessor.

## Completion definition

P158 is complete when:

- all P154-P158 frozen tests, lint, typecheck, artifact freshness, and source
  binding checks pass;
- P154 demonstrates a valid longitudinal recorded ledger;
- P155 resolves evidence gaps within read budgets;
- P156 improves or preserves diagnosis quality without unsafe model authority;
- P157 proves lab action post-check and rollback closure;
- P158 emits a truthful maximum authority level and explicit production
  blockers.

P158 completion is not equivalent to production operator replacement.
