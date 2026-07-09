# OpsCat Operator Walkthrough

This walkthrough is the reviewer-facing path for OpsCat as a local/mock agentic operator. It explains what an operator sees and what evidence supports each stage.

1. observe — OpsCat starts from provider-shaped alert or fixture evidence and captures service, severity, environment, and timeline state.
2. correlate — Signals are grouped with deployment, metric, and incident context so likely relationships are visible.
3. investigate — Read-only local/mock context tools produce evidence-grounded hypotheses and candidate causes.
4. decide — Readiness, confidence, policy, and evidence gates decide whether to proceed, hand off, or block.
5. draft — OpsCat prepares report, ticket, rollback, or remediation drafts as metadata, not uncontrolled production mutation.
6. act safely — P93 records zero executions and only points to local/mock dry-run evidence; live or production execution remains forbidden.
7. verify — Acceptance evidence proves whether a local/mock path is demo-ready, shadow-only, human-gated, or blocked.
8. report — Markdown and release docs make incident and portfolio evidence inspectable.
9. improve — Roadmap and release evidence keep remaining gaps explicit so the portfolio does not overstate production maturity.

Run the pack:

```bash
uv run --no-sync --extra dev python scripts/run_portfolio_demo_pack.py
```

Expected output includes `walkthrough_steps>=8 proof_points>=6 commands>=3 executions=0`.

Boundary: no auth work, no live APIs, no credentials, no network, no production mutation, no real remediation/action execution, and no external model/API calls.
