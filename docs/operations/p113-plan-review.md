# P113 plan review

## Initial verdict

`REJECT` before execution. Independent criticism found that the initial
direction did not yet define a strict consumed-blind taint boundary, separate
deterministic/provider/action result surfaces, raw-versus-normalized compliance,
all-fault floors, or replay for invalid provider output.

## Required amendments applied

- Added a machine-enforced taint ledger and prohibited all P112 repetition-4
  case-level material from P113 release development.
- Named three independent result surfaces: `deterministic_judgment`,
  `llm_advisory`, and disabled `action_contract_status`.
- Required separate raw and normalized provider-contract metrics so bounded
  normalization cannot hide noncompliance.
- Added CPU, memory, disk, delay, and loss per-fault floors.
- Required replay from frozen packet hashes for invalid responses that omit
  candidate context.
- Declared all 125 Train Ticket cases as fresh blind evidence and prohibited TT
  label scoring before freeze.

## Execution gate

Implementation may begin only after an independent critic confirms these
amendments are sufficient. Release remains impossible without fresh TT blind
evidence and an out-of-band cryptographic reviewer.
