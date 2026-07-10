# P103 Multi-step LLM Diagnostic Episode

## Outcome

Turn P102's one-shot advisory choice into a bounded diagnostic episode that can
observe a negative read-only result, revise the next choice, stop on correlated
evidence, and delegate remediation to the deterministic P100 policy boundary.

## Tickets

- P103-001 episode state and history contract
- P103-002 negative-result replanning
- P103-003 positive-evidence handoff
- P103-004 repeated-tool prevention
- P103-005 maximum tool-call budget
- P103-006 malformed/provider-failure escalation
- P103-007 scorer-truth isolation
- P103-008 heuristic/fixed/LLM equal-state comparison
- P103-009 strict tool-selection metrics
- P103-010 outcome-based recovery metrics
- P103-011 offline and opt-in NVIDIA CLI
- P103-012 tests, evidence, and release verification

## Stop condition

The default episode must remain deterministic and network-free, execute only
closed synthetic read-only diagnostics, never repeat a failed tool, stop within
budget, and leave all actions to P100's closed-registry policy. Comparison must
separate strict first-tool accuracy from measured end-to-end recovery.
