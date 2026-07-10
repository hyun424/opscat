# OpsCat P97 Final Summary — Causal Remediation Benchmark

P97 is implemented. OpsCat can now test whether a remediation decision **causes** measurable recovery inside a disposable synthetic local fault lab. The runner resets the same case and seed for `no_action`, `human_runbook`, and `opscat`, performs real loopback HTTP workload observations, applies only fixed in-memory lab actions, and derives the result from post-action service behavior rather than fixture-provided expected status.

## Completed tickets

- P97-001 — Benchmark contract and RED tests were committed before production implementation.
- P97-002 — `IsolatedFaultLab` binds to an ephemeral `127.0.0.1` port and serves a real HTTP workload while keeping actions inside a closed in-memory registry.
- P97-003 — The deterministic catalog contains 120 cases: 12 operational families × 10 variants, split 72 development / 24 validation / 24 blind.
- P97-004 — Every case and seed is replayed through `no_action`, `human_runbook`, and `opscat` from the same initial fingerprint.
- P97-005 — The OpsCat selector receives only opaque case ID, symptom, visible evidence, measurements, allowed lab actions, and boundary metadata; family, variant, split, hidden required actions, harmful-action maps, and runbook answers are not passed to it.
- P97-006 — The report derives effective, partially effective, no effect, harmful, unverified, or baseline outcomes and calculates recovery, causal lift, durability, regret, escalation, and per-family metrics.
- P97-007 — Out-of-scope mutation, unknown action execution, unsafe action, data loss, false recovery declaration, and initial-state mismatch are hard safety gates.
- P97-008 — `scripts/run_causal_remediation_benchmark.py` provides a bounded 12-case smoke by default and a 120-case repeated `--full-matrix` mode.
- P97-009 — Targeted tests, lint, mypy, release contracts, verification integration, and full-matrix evidence are included.

## Full-matrix measured result

Command:

```bash
uv run --no-sync --extra dev python scripts/run_causal_remediation_benchmark.py \
  --full-matrix \
  --output-json /tmp/opscat-p97-full.json \
  --output-md /tmp/opscat-p97-full.md
```

The completed run evaluated **120 cases**, **3 deterministic seeds**, **3 intervention arms**, and **1,080 trials** using **64,800 actual loopback HTTP requests**.

- OpsCat recovery rate: **44.17%**
- Human-runbook recovery rate: **90.0%** after the P100 catalog-consistency correction
- No-action recovery rate: **16.67%**
- OpsCat causal recovery lift over no-action: **0.275**
- Mean utility lift over no-action: **0.1281**
- Durable recovery rate: **44.17%**
- Action-effectiveness precision: **83.02%**
- Escalation correctness and precision on scorer-only missing/conflicting/human-required truth: **100%**, across 129 expected-escalation trials
- Unverified rate: **10%**
- Harmful action rate for the included OpsCat baseline: **0%**
- Harness execution-valid gate: **passed**, with every forbidden-event counter at zero; no performance pass threshold is claimed

## Honest interpretation

The result is useful because it exposes a real gap instead of manufacturing a perfect score: the fixed evidence-only OpsCat baseline recovers fewer cases than the curated human runbook. The largest expected gaps are multi-step remediation, privileged security/auth cases, partial recovery, and evidence that must be escalated rather than acted on. P97 turns those gaps into measurable future optimization targets for deterministic and LLM selectors.

The action-effectiveness precision is conditional on cases where this baseline chose a state-changing lab action. It must not be read as 83.02% end-to-end operator replacement: overall OpsCat recovery is 44.17%, and 10% of outcomes remain unverified. The `first_action_ineffective` variants deliberately require the runbook to observe one ineffective mitigation and continue, exposing the current one-step selector gap.

## Safety and claim boundary

- The server binds only to `127.0.0.1` on an ephemeral port.
- Workload probes use direct `http.client` loopback connections and do not honor proxy environment variables.
- HTTP destinations are created internally and cannot be supplied by a benchmark case or model.
- Actions are fixed names that mutate only disposable in-memory lab state.
- `observe` and `escalate` routes cannot execute state-changing actions; inconsistent route/action output is blocked and fails the harness safety gate.
- There is no arbitrary shell, subprocess, filesystem mutation, credential access, external network, provider write, production connector write, or production mutation.
- The existing product action path remains unchanged and mock/safety-gated.
- P97 **does not prove production remediation effectiveness** and is not production evidence. It proves that OpsCat now has a reproducible causal evaluation harness in a synthetic local fault lab.

## Next handoff

P98 should plug multiple selectors into the same evidence-only interface—current deterministic baseline, NVIDIA LLM, and ablations—then improve blind-split causal recovery without regressing hard safety gates, natural-recovery restraint, escalation correctness, or human-runbook regret.
