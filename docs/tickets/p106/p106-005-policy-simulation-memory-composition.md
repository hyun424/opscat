# P106-005 - Policy, Simulation, Blast-Radius, and Memory Composition

## Goal

Compose the existing safety infrastructure instead of duplicating policy logic.

## Contract

- Composition graph:
  `shared RiskEngine -> PolicyEngine(shared RiskEngine) ->
  policy_engine.blast_radius_service + policy_engine.action_simulator`, plus
  `IncidentMemory`.
- Each selected candidate stores policy, simulator, blast-radius, and memory
  outputs in its decision trace.
- Registry hash/object parity is checked before candidate evaluation.
- P106 source and CLI modules must not import, reference, alias, or call
  `ActionService.execute`, `MockActionExecutor`, `execute_mock_action`,
  `start_action_attempt`, or `record_execution_result`.

## Acceptance

Policy denials, unknown capabilities, simulation gaps, unknown blast radius,
prior failed remediation, registry divergence, or forbidden execution API
references prevent selection. `PolicyDecision.ALLOW` still returns a
simulation-only P107 handoff.
