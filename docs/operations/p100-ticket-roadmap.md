# P100 Stateful Multi-step Incident Investigator

## Outcome

Replace one-shot action selection with a bounded incident session that can select an
initial mitigation, observe measured results, reject an ineffective hypothesis,
choose a second action, prove durable recovery, or stop and escalate safely.

## Tickets

- **P100-001 — Session contract and RED tests**
  - Lock step history, public evidence boundary, maximum step budget, stop reasons, output schema, and safety gates before implementation.
- **P100-002 — Evidence-only operational playbooks**
  - Map visible operational markers to ordered candidate actions without exposing case family, variant, required actions, harmful actions, or expected outcomes.
- **P100-003 — Stateful decision history**
  - Persist attempted actions and measured pre/post deltas while withholding scorer-only action-effect labels from the agent.
- **P100-004 — Failed-first-action recovery**
  - Detect no measurable progress and try the next bounded candidate instead of repeating or declaring recovery.
- **P100-005 — Partial and compound remediation**
  - Continue after partial improvement until recovery, step budget, safety stop, or escalation.
- **P100-006 — Natural-recovery restraint**
  - Observe without mutation when evidence indicates a decaying transient and stop once measured recovery is proven.
- **P100-007 — Privileged and ambiguous evidence gates**
  - Escalate with zero mutation on privileged, missing, conflicting, or unsupported evidence.
- **P100-008 — Worsening and collateral stop**
  - Stop immediately if utility degrades materially or collateral regression appears; never continue an unsafe chain.
- **P100-009 — Four-arm causal benchmark**
  - Compare `no_action`, `human_runbook`, `one_shot`, and `stateful_agent` from identical initial states.
- **P100-010 — Broad 520-case evaluation**
  - Report overall, development/validation/blind, per-family, step-count, recovery, durability, regret, escalation, and safety metrics.
- **P100-011 — Performance and safety gates**
  - Require stateful blind recovery above one-shot, stateful overall recovery above one-shot, harmful actions at zero, escalation correctness at 100%, and every hard safety counter at zero.
- **P100-012 — CLI, reports, and release verification**
  - Add bounded smoke/full matrix commands, JSON/Markdown evidence, targeted tests, Ruff, mypy, full regression, and documentation contracts.

## Stop condition

P100 is complete when the stateful agent improves overall and blind measured recovery
over the same one-shot selector on the full P99 catalog, handles ineffective and
partial first actions through re-observation, preserves zero harmful action and 100%
escalation correctness, and passes every hard safety gate. It remains a synthetic
loopback evaluation and does not authorize production remediation.
