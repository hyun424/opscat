# P115 plan review

## Decision: accepted as an offline benchmark-contract phase

The P115 plan is accepted only under a constrained claim: it defines how
remediation decisions will be represented, partitioned, checked for leakage,
and scored after measured P116 outcomes exist. It does not claim action
effectiveness by itself.

## Required constraints incorporated

- P114 remains a diagnosis boundary; P115 consumes sealed evidence and
  hypothesis IDs, not hidden truth or action authority.
- Auth is deferred and cannot be required for any P115 acceptance gate.
- Action authority is disabled; action packs are declarative benchmark
  metadata, not executable permission.
- `no_action`, `investigate_more`, and `escalate` are first-class correct
  outcomes rather than failures to remediate.
- Final scoring requires P116 measured paired outcomes for action, no-action,
  and wrong-action arms.
- Scenario-family and action-family denominators are reported separately so an
  aggregate cannot hide collapse.
- The optional LLM benchmark is constrained to frozen action-pack IDs and may
  not emit commands or unregistered actions.

## Residual risks

- P116 may later fail to generate enough measured paired outcomes, leaving P115
  in `p115_contract_ready` rather than `p115_outcome_qualified`.
- Scenario families can still overfit if source, topology, time, and action
  pack grouping are too coarse.
- Declarative validation and rollback metadata may look complete before P116
  proves that the corresponding interventions are measurable and reversible.
- Human-authored action packs may encode hidden hints unless reviewer-owned
  leakage probes attack field names, descriptions, IDs, and ordering.

## Review verdict

Implementation may proceed only within the P115 document and offline benchmark
authority boundary. Any code implementation must preserve exact-zero counters
for auth, credentials, execution, mutation, production adapters, and action
authority. Portfolio or release claims about remediation quality remain blocked
until P116 measured outcomes are imported and independently reviewed.
