# OpsCat P100 Final Summary — Stateful Multi-step Incident Investigator

P100 replaces the one-shot remediation selector with a bounded incident session.
The agent observes public evidence, chooses one enumerated action, measures the
result, updates a sanitized history, and either tries the next evidence-backed
step, proves recovery, or escalates without mutation.

## What changed

- Added 52 evidence-only ordered playbooks without case IDs, variants, hidden
  required actions, harmful-action labels, or expected outcomes.
- Added a maximum three-step stateful coordinator with one action per step.
- Added failed-first-action fallback and partial/compound remediation completion.
- Added read-only natural-recovery confirmation, including privileged incidents
  where observation is safe but mutation is not.
- Added a second observation before accepting a noisy material-worsening signal.
- Added immediate stop on collateral regression, confirmed worsening, unsupported
  output, exhausted playbook, escalation, or step budget.
- Added a four-arm benchmark: `no_action`, `human_runbook`, `one_shot`, and
  `stateful_agent`, all reset to the same case/seed fingerprint.
- Fixed a catalog integrity bug where a secondary required/runbook action could
  also be labeled harmful in two scenario variants.

## Full matrix measured result

Command:

```bash
./.venv/bin/python scripts/run_stateful_incident_investigator.py \
  --seeds 11,29,47 --sample-size 10 --max-steps 3 \
  --output-json /tmp/opscat-p100-full.json \
  --output-md /tmp/opscat-p100-full.md
```

- Catalog: **52 families / 520 cases**
- Seeds: **3**
- Arms: **6,240 trials**
- Actual loopback HTTP requests: **183,990**
- Stateful recovery: **56.47%** (**881 / 1,560**)
- Stateful durable recovery: **56.35%** (**879 / 1,560**)
- One-shot recovery: **34.55%**
- No-action recovery: **11.47%**
- Curated human-runbook recovery: **89.87%**
- Stateful lift over one-shot: **+21.92 percentage points**
- Stateful lift over no-action: **+45.00 percentage points**
- Development recovery: **64.00%** versus one-shot **39.64%**
- Validation recovery: **50.96%** versus one-shot **50.96%**
- Blind recovery: **39.42%** versus one-shot **2.88%**
- Average stateful decision steps: **1.225**
- Stateful collateral regressions: **0**
- Unknown/unsafe/out-of-scope executions: **0**
- Every hard safety gate: **passed**

The final escalation scorer treats a visible, negative-slope natural-recovery
pattern as a safe read-only observation path rather than a mutation requiring
approval. Under that contract, the expected and actual escalation sets both contain
678 case/seed arms, giving **100% recall and 100% precision**.

## Interpretation

The 34.55% one-shot score was not a ceiling on the scenario set. Re-observation
and bounded second actions recover ineffective-first-action, partial, and compound
cases that a single decision cannot solve. The blind split improvement from 2.88%
to 39.42% is the strongest evidence that stateful behavior matters.

The remaining 33.40-point gap to the curated human runbook is also important.
P100 still uses deterministic marker playbooks, a synthetic in-memory action model,
and a maximum of three steps. It does not yet perform open-ended hypothesis search,
request new diagnostic tools, learn organization-specific topology, or prove that
the same action would work on a real production service.

## Safety and claim boundary

- The agent sees only public observation fields and sanitized measured history.
- Scorer-only truth and lab action-effect strings never enter agent context.
- All mutations are closed-registry in-memory transitions behind `127.0.0.1`.
- No shell, filesystem, credential, external network, connector write, or production
  mutation is available.
- P100 proves a stateful agent loop in a causal synthetic lab; it does not prove
  unattended production safety or full operator replacement.

## Next handoff

P101 should replace static playbook selection with an evidence-planning interface:
the agent chooses diagnostic tools, maintains competing hypotheses, requests the
minimum discriminating evidence, and only then proposes a policy-gated action.
That evaluation should include hidden topologies and unseen evidence wording so
success cannot come from matching a fixed marker alone.
