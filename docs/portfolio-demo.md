# OpsCat Portfolio Demo

OpsCat is a local/mock agentic AI incident-response/operator-replacement evidence system. It is meant to show how an operator loop can use tools, ground decisions in evidence, apply safety policy, hand off to humans, verify outcomes, and report results without claiming production autonomy.

## One-command demo

```bash
uv run --no-sync --extra dev python scripts/run_portfolio_demo_pack.py
```

Expected smoke line:

```text
walkthrough_steps>=8 proof_points>=6 commands>=3 executions=0
```

The command writes:

- `/tmp/opscat-portfolio-demo-pack-latest.json`
- `/tmp/opscat-portfolio-demo-pack-latest.md`

## Evidence chain

- P92 acceptance smoke: `uv run --no-sync --extra dev python scripts/run_operator_replacement_acceptance_drill_v3.py`
- Docs profile: `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile docs`
- Full local release gate: `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

## Role signals

- Tool use: provider-shaped readers, correlation, runbook, policy, verification, reporting, and evidence-pack tools.
- Evidence-grounded reasoning: hypotheses, decisions, stages, reports, and proof points cite local evidence.
- Policy/safety gates: risk, approval, readiness, and forbidden-claim gates are explicit.
- Autonomous loop: observe, correlate, investigate, decide, draft, act safely, verify, report, and improve.
- Evaluation/benchmarking: deterministic drills, docs tests, release evidence, and verify profiles.
- Human approval handoff: protected or high-risk paths remain human-gated.
- Local/mock dry-run boundary: executions, live calls, credentials, network, production mutation, and external model calls stay at zero.

Boundary: P93 is local/mock portfolio evidence only and not production autonomy.
