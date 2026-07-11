# P108-001 - Immutable Outcome Ledger

Create a hash-linked append-only ledger joining P104 evidence, P105 forecast,
P106 plan/policy, and P107 audit/outcome references. Enforce sequence, parent,
content-hash, idempotency, and immutable temporal cutoffs.

Done when duplicate equivalent appends are idempotent and truncation, mutation,
forks, sequence gaps, or ID reuse with different content fail closed.
