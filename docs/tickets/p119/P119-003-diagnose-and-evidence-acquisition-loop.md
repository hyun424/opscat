# P119-003: diagnose and evidence acquisition loop

## Goal

Bind P114/P117-compatible diagnosis episodes, preserve competing hypotheses,
identify missing or contradictory evidence, and acquire only approved
local/mock/sandbox fixture evidence from a frozen taxonomy.

## Contract

- Bind diagnosis to sealed visible evidence, source hashes, fixture IDs,
  budget snapshots, and P117-compatible episode refs.
- Preserve hypotheses, falsification events, contradictions, missing evidence,
  and abstention markers in the timeline.
- Request evidence only from the frozen local fixture taxonomy with typed,
  declarative evidence requests.
- Record evidence receipts with source hash, acquisition budget, redaction
  receipt, and timeline event refs.
- Route missing, stale, contradictory, contaminated, or value-negative evidence
  to investigate-more, abstention, escalation, or fail-closed behavior.

## Acceptance

Evidence requests are typed and budgeted, evidence receipts are hash-bound,
contradictions remain visible, missing required evidence never forces action,
and no live connector, credential, production, network, shell, subprocess, or
untrusted command path exists.

## Stop Rules

Stop if evidence acquisition can call live providers, read credentials, access
production or staging targets, execute commands, mutate network/database/cloud/
Kubernetes state, hide contradictions, invent evidence, tune after frozen
scoring, or proceed to action with missing required evidence.
