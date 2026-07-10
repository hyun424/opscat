# P104 Evidence Gap Investigator

## Outcome

Build the evidence-gap layer that decides whether a diagnostic hypothesis has
enough fresh, non-conflicting, multi-source evidence before any action handoff.
P104 extends the P101/P103 read-only diagnostic loop from "find a correlated
tool result" to "prove sufficiency or explain the exact evidence gap."

The investigator must return a shared decision envelope that later P105-P108
phases can consume without inventing phase-local evidence shapes. It may select
the next read-only diagnostic tool, ask an optional strict LLM provider for an
evidence-gap proposal, or escalate with a structured gap payload. It must not
execute actions, mutate production, add auth scope, leak scorer truth, or treat
LLM confidence as authority.

## Existing Baseline

- P101 defines the closed read-only diagnostic tool catalog and synthetic
  diagnostic lab in `app/services/tool_using_hypothesis_investigator.py`.
  `_DiagnosticLab.query()` currently returns all useful evidence from one
  expected tool and no evidence from every other tool, which is too simple for
  partial, conflicting, stale, unavailable, or distracting evidence.
- P102 defines strict provider JSON validation in
  `app/services/llm_tool_planner_evaluation.py`: provider output can select a
  registered read-only tool or escalate, but cannot execute tools or actions.
- P103 wraps that provider into a bounded multi-step diagnostic episode in
  `app/services/llm_diagnostic_episode.py`, removes attempted tools from the
  next catalog, counts model calls explicitly, prevents repeated tools, and
  delegates action only after any positive evidence.
- P100's `StatefulEvidenceAgent` in
  `app/services/stateful_incident_investigator.py` already blocks low telemetry,
  privileged scope, and conflicting evidence. P104 should preserve that
  downstream policy boundary and add a stronger upstream sufficiency gate.

## Non-Goals and Boundaries

- No auth, credential, connector, or production-environment feature work.
- No production mutation, remediation execution, or new action authority.
- No mutating diagnostic calls; P104 tools remain closed, local, read-only, and
  side-effect free.
- No scorer leakage: provider context and public envelopes exclude family,
  variant, split, expected tool, required action, harmful action, runbook answer,
  private outcome label, and hidden scorer truth.
- No online learning or threshold auto-tuning. P104 produces offline benchmark
  evidence only.
- No `docs/operations/p104-plan-review.md`; independent review owns that file.

## Target Artifacts

- `app/services/evidence_gap_investigator.py`
- `scripts/run_evidence_gap_investigator.py`
- `tests/test_evidence_gap_investigator.py`
- `tests/test_p104_release_evidence.py`
- `evals/evidence_gap/seed/scenarios.json`
- `docs/operations/p104-ticket-roadmap.md`
- `docs/tickets/p104/README.md`
- `docs/tickets/p104/p104-000-shared-decision-envelope.md`
- `docs/tickets/p104/p104-001-evidence-requirement-contract.md`
- `docs/tickets/p104/p104-002-evidence-state-model.md`
- `docs/tickets/p104/p104-003-partial-conflicting-evidence-lab.md`
- `docs/tickets/p104/p104-004-sufficiency-hard-gates.md`
- `docs/tickets/p104/p104-005-information-value-tool-selection.md`
- `docs/tickets/p104/p104-006-strict-llm-gap-proposal.md`
- `docs/tickets/p104/p104-007-budget-and-fail-closed-controls.md`
- `docs/tickets/p104/p104-008-escalation-payload.md`
- `docs/tickets/p104/p104-009-equal-state-benchmark.md`
- `docs/tickets/p104/p104-010-cli-docs-release-integration.md`

## Ticket Sequence

### P104-000 - Shared Decision Envelope

Define the cross-phase envelope before implementation:
`episode_id`, `decision_id`, `schema_version`, `hypothesis_id`,
`requirement_set_id`, `evidence_states`, `sufficiency_decision`, provenance,
freshness, trace IDs, budget counters, model-call counters, and boundary flags.
The envelope must distinguish `inspect_next`, `sufficient_for_policy_handoff`,
`escalate_gap`, and `abstain_fail_closed`.

Tests first:

- envelope constructors reject missing IDs, duplicate evidence IDs, invalid
  states, negative budgets, and unknown routes;
- `to_public_provider_packet()` strips scorer-only fields;
- JSON round trip is stable and sorted enough for golden fixture comparison;
- downstream adapter to the P100 action boundary only accepts
  `sufficient_for_policy_handoff`.

### P104-001 - Evidence Requirement Contract

Introduce typed `EvidenceRequirement` records for each hypothesis. Requirements
must express source family, tool candidates, criticality, accepted evidence
states, freshness window, contradiction policy, and why the requirement matters.

Tests first:

- critical requirements cannot be optional;
- each action-ready hypothesis has at least one critical requirement and one
  contradiction check;
- unsupported tool IDs fail validation against P101's closed catalog;
- no requirement can name scorer-only outcome labels or required actions.

### P104-002 - Evidence State Model

Represent supporting, contradicting, absent, stale, unavailable, distracting,
duplicate, and not-yet-queried evidence as first-class states. P104 must
separate "tool returned valid absence" from "tool unavailable/no data."

Tests first:

- stale evidence cannot satisfy a freshness-bound requirement;
- unavailable evidence records capability/tool failure separately from absence;
- duplicate evidence is counted once and reported as duplicate;
- conflicting evidence blocks action handoff even when one source supports the
  hypothesis.

### P104-003 - Enhanced Partial and Conflicting Evidence Lab

Replace the P101 single-expected-tool lab behavior for P104 benchmark cases with
a richer fixture-backed lab that can return partial support, contradictions,
stale readings, telemetry outages, distractors, prompt-injected log content,
duplicate results, blocked tool capability, and natural recovery.

Tests first:

- each required scenario class is covered by a deterministic fixture;
- lab output contains only public read-only evidence, not expected tool,
  required action, hidden family answer, or scorer label;
- prompt-injected log content remains inert text and cannot add routes, tools,
  credentials, shell commands, or actions;
- natural recovery while evidence is gathered produces observe/escalate, not an
  action-ready handoff.

### P104-004 - Sufficiency Hard Gates

Implement deterministic sufficiency scoring with hard gates. An action-ready
decision requires every critical requirement to be fresh and satisfied, no
unadjudicated contradiction, adequate telemetry coverage, no unavailable
critical capability, and an explicit evidence-to-claim citation list.

Tests first:

- missing, stale, unavailable, or contradicted critical evidence blocks handoff;
- optional supporting evidence can raise score but cannot override hard gates;
- contradiction cases remain blocked until adjudicated or escalated;
- every action-ready decision cites all critical requirement IDs and evidence
  IDs.

### P104-005 - Information-Value Tool Selection

Select the next read-only tool by deterministic information-value proxy instead
of by expected scorer label. Rank tools by unresolved critical requirements,
ability to resolve contradictions, freshness gaps, prior attempts, and cost.

Tests first:

- highest-value tool targets the most important unresolved critical gap;
- repeated tool execution is impossible unless a requirement explicitly allows a
  refresh after stale evidence, and the refresh has a new trace ID;
- unavailable tools are not selected again in the same episode;
- tool ranking never consumes hidden expected-tool labels.

### P104-006 - Optional Strict LLM Gap Proposal

Add an optional provider path that proposes missing evidence and next tool under
strict schema validation. The model may propose `inspect_next` or
`escalate_gap`; it cannot declare sufficiency, authorize action, add tools, add
arguments, request credentials, or override deterministic gates.

Tests first:

- malformed JSON, extra fields, unknown tools, action fields, shell text,
  credentials, route conflicts, and provider exceptions fail closed;
- provider packet contains public observation, sanitized evidence states,
  requirement summaries, closed read-only catalog, and remaining budget only;
- default tests and CLI mode make zero network/model calls;
- live NVIDIA mode, if wired, is explicit opt-in, bounded, and advisory-only.

### P104-007 - Budgets and Fail-Closed Escalation Controls

Enforce tool-call budget, wall-clock/step budget, provider-call budget, and
provider-failure behavior. Exhaustion must produce `escalate_gap` with the
specific missing evidence and next unavailable capability.

Tests first:

- invalid budget bounds fail at construction or CLI parsing;
- tool, provider, and wall-clock exhaustion execute no action;
- repeated provider failures trip fail-closed escalation;
- all budget counters appear in the envelope and benchmark report.

### P104-008 - Exact Escalation Payload

Standardize the payload for abstention/escalation: missing requirements,
contradictions, stale evidence, unavailable capabilities, already attempted
tools, proposed next read-only capability, and operator-facing rationale.

Tests first:

- every abstention includes at least one actionable gap;
- contradiction payloads include both supporting and contradicting evidence IDs;
- unavailable-tool payloads name the capability without inventing auth or
  production connector work;
- escalation payloads redact secrets and prompt-injected instructions.

### P104-009 - Equal-State Benchmark

Benchmark P104 against P103 and fixed-tool baselines from identical initial lab
states. Report false-remediation handoff rate, valid-case recovery retention,
gap quality, contradiction blocking, repeated tool count, sufficiency precision,
and distinction between valid absence and no data.

Tests first:

- every arm for a case/seed starts from the same fingerprint;
- benchmark rows separate strict tool choice, sufficiency correctness,
  action-ready handoff, and downstream recovery;
- false-remediation handoff rate is lower than P103 on partial/conflicting cases
  without reducing valid-case recovery by more than two percentage points;
- hard safety counters for scorer leakage, repeated tools, action execution,
  mutation, unknown tools, and state mismatch are zero.

### P104-010 - CLI, Docs, Release Evidence, and Verification

Add the offline CLI, report writer, release docs, verification script entries,
and final evidence summary once implementation and independent review pass.

Tests first:

- CLI rejects invalid bounds without traceback;
- default CLI writes JSON and Markdown reports with no model/network calls;
- release evidence test checks roadmap, docs, README, `docs/release-evidence.md`,
  `ROADMAP.md`, and `scripts/verify.sh` references;
- verification profile includes targeted tests plus the P104 smoke command.

## Required Scenario Coverage

- supporting evidence split across metrics and logs;
- one positive source contradicted by traces or deployment metadata;
- no data because telemetry failed versus valid data showing no anomaly;
- stale evidence that must not satisfy the gate;
- misleading distractor evidence;
- critical evidence available only through a blocked or unavailable tool;
- repeated/duplicate evidence;
- prompt-injected log content;
- natural recovery while evidence is gathered.

## Acceptance Criteria

- 100% of action-ready decisions cite all critical evidence requirements.
- 100% of contradiction cases block action handoff until adjudicated or
  escalated.
- 0 repeated tool executions except explicitly allowed freshness refreshes, and
  those must be counted separately from duplicates.
- 0 mutating diagnostic calls, action executions by provider output, production
  mutations, credential reads, or auth-scope expansions.
- 0 scorer-truth fields in provider context or public reports.
- False-remediation handoff rate is lower than P103 on partial/conflicting cases
  without reducing valid-case recovery by more than two percentage points.
- Every abstention reports an actionable, specific evidence gap.
- Benchmarks prove that valid absence and telemetry/tool unavailability are
  represented and scored differently.

## Verification Plan

Expected implementation verification:

```bash
./.venv/bin/python -m pytest tests/test_evidence_gap_investigator.py
./.venv/bin/python -m pytest tests/test_p104_release_evidence.py
./.venv/bin/python scripts/run_evidence_gap_investigator.py \
  --max-cases 16 --sample-size 5 --output-json /tmp/opscat-p104.json \
  --output-md /tmp/opscat-p104.md
./scripts/verify.sh fast
./scripts/verify.sh docs
```

Optional live-provider verification, only after deterministic gates pass and
with explicit opt-in:

```bash
./.venv/bin/python scripts/run_evidence_gap_investigator.py \
  --include-nvidia --max-cases 16 --sample-size 5 \
  --output-json /tmp/opscat-p104-nvidia.json \
  --output-md /tmp/opscat-p104-nvidia.md
```

## Stop Condition

P105 cannot start until P104's benchmark proves that evidence not found and
evidence proving absence are represented and scored differently, contradiction
cases block action handoff, scorer truth remains private, and every action-ready
decision cites all critical evidence through the shared decision envelope.
