# OpsCat P98 Final Summary — Selector Comparison and Blind Causal Evaluation

P98 adds a comparison layer over P97 so selector quality is measured by observed
recovery and side effects, not by plausible analysis text.

## Implemented

- Added an evidence-only JSON adapter for deterministic and external decision providers.
- Added fail-closed handling for malformed JSON, invalid routes, unknown actions,
  observe/action contract violations, and recovery claims.
- Added deterministic `rule_based`, `observation_only`, and `mock_llm` selectors.
- Added an explicit `NvidiaCausalDecisionProvider`; it requires `NVIDIA_API_KEY` or
  an injected client, is never selected by default, and only proposes a decision.
- Added selector comparison output with overall, development/validation/blind split,
  per-family, safety, harmful-action, escalation, and runbook-regret metrics.
- Added P98 tickets, plan review, release evidence, CLI smoke, and regression tests.

## Full matrix result

Command:

```bash
./.venv/bin/python scripts/run_selector_comparison.py \
  --full-matrix --output-json /tmp/opscat-p98-full.json
```

The run compared 3 selectors over 120 cases, 3 deterministic seeds, and the same
P97 loopback lab. Each selector contributed 360 OpsCat decision arms (1,080
selector arms total; 3,240 total arms including no-action and human-runbook
controls) and passed the hard safety gate.

| Selector | Overall recovery | Blind recovery | Blind causal lift | Harmful actions | Unverified |
| --- | ---: | ---: | ---: | ---: | ---: |
| rule_based | 44.17% | 12.50% | 0.0417 | 0% | 10% |
| mock_llm | 44.17% | 12.50% | 0.0417 | 0% | 10% |
| observation_only | 16.67% | 8.33% | 0.0000 | 0% | 10% |

The current mock LLM is intentionally a protocol baseline, not a quality claim: it
matches the deterministic rule selector. The benchmark therefore shows that merely
putting an LLM-shaped interface around the same policy does not improve operations.
The next meaningful improvement must increase blind causal recovery without raising
harmful actions, false recovery, or escalation errors.

## Safety and claim boundary

- Selector prompts contain only P97 public observation fields; hidden family, variant,
  split, required actions, harmful actions, and expected outcomes remain scorer-only.
- NVIDIA access is explicit opt-in. No API call occurred in the default tests or the
  recorded full matrix.
- The LLM never executes tools. P97's closed in-memory loopback lab is the only action
  executor in this evaluation.
- All selectors had zero unknown action execution, out-of-scope mutation, false
  recovery declaration, route contract violation, and unsafe action events.
- This is comparative synthetic-lab evidence. It does not prove production
  remediation effectiveness or operator replacement.
