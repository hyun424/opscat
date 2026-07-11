# P117 Independent-Style Plan Review

## Decision: accepted as proposal-only action selection

P117 is accepted only as an evidence-bound action-selection and abstention
phase. It may rank frozen P115 action-pack IDs, request typed evidence, choose
first-class non-action labels, and compare deterministic and NVIDIA proposal
selectors. It does not grant execution authority or production remediation
permission.

## Required Constraints Incorporated

- P114 remains the diagnosis boundary. P117 consumes sealed lattices, selected
  hypothesis IDs or abstention, visible evidence IDs, freeze receipts, and
  replay receipts.
- P115 remains the action-contract boundary. P117 consumes signed action-pack
  IDs and first-class abstention labels, not free-form actions.
- P116 remains the measured-outcome boundary. P117 final utility scoring is
  blocked without hash-bound measured paired outcomes.
- Active evidence acquisition is modeled as declarative benchmark output, not a
  live connector call or authority grant.
- Contradictions are ledgered and can force utility penalties, fallback,
  evidence acquisition, or abstention.
- Utility, calibration, and abstention are explicit release gates rather than
  advisory diagnostics.
- Deterministic selection is the baseline and fallback. NVIDIA is proposal-only
  and cannot override deterministic gates.
- Frozen unseen evaluation is consumed on first score; no tuning from unseen
  labels is allowed.
- All production authority, credential, execution, mutation, and online policy
  counters remain exactly zero.

## Adversarial Concerns

- An "action-selection agent" can be misread as an executor. P117 therefore
  binds every output to frozen IDs and requires `p118_required_for_execution`.
- Evidence acquisition can become a covert live connector capability. P117
  restricts it to a frozen taxonomy and declarative benchmark labels.
- NVIDIA may produce fluent but unsafe action prose. P117 treats all LLM output
  as untrusted proposal data and fails closed to deterministic fallback.
- Measured utility can be faked by missing denominators or natural recovery.
  P117 requires P116 paired outcomes and nullable metric preservation.
- Aggregate tournament wins can hide harmful families. P117 requires per-family,
  per-action-family, per-label, and disagreement reports.
- Contradictions can be erased by confidence averaging. P117 requires an
  explicit contradiction ledger and thresholded fallback semantics.

## Residual Risks

- P116 may not produce enough measured outcomes, leaving P117 in
  `p117_contract_ready` rather than final utility-qualified status.
- Deterministic utility thresholds may be too conservative or too aggressive;
  frozen unseen evaluation and calibration reports must expose this rather than
  retune silently.
- NVIDIA proposal quality may depend on prompt and model stability; repeat
  agreement and fallback rates are required before any comparative claim.
- Evidence-acquisition value may be difficult to estimate without real
  connector latency/cost; P117 should claim benchmark selection quality only,
  not production investigation efficiency.

## Review Verdict

Implementation may proceed only within the P117 planning boundary: schema,
offline selector, proposal parser, evaluator, release evidence, and tests. Any
future code must preserve exact-zero counters for auth, credentials, execution,
mutation, production adapters, live connector calls, and action authority.

Portfolio, release, or model-card claims may say "evidence-bound action
selection benchmark" only after frozen unseen gates pass. They may not say
"autonomous remediation", "production-safe action execution", or "operator
replacement".

## Stop Conditions

Stop before implementation or release if any requirement pressures P117 to
execute actions, retrieve live evidence, authenticate, use credentials, mutate
systems, consume hidden labels, invent IDs, trust LLM prose, tune on unseen
results, ignore contradictions, report missing denominators as success, or
weaken deterministic fallback authority.
