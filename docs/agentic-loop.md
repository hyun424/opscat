# OpsCat Agentic Loop

OpsCat's P6 beta loop is: **observe → correlate → diagnose → plan → risk → act → verify**.

```text
fixture/provider-shaped signal
  -> observe and normalize
  -> correlate workspace-scoped evidence
  -> diagnose ranked root cause
  -> plan bounded runbook steps
  -> risk-score policy decision
  -> act only in local/mock or approval-gated paths
  -> verify recovery and write audit/report evidence
```

The loop is agentic because decisions are staged, stateful, tool-mediated, policy-gated, and verified. It is not production-ready: auth remains deferred, default connectors are fixture/local, and production mutations are unavailable.

## Reproduce the local/mock loop

```bash
python scripts/demo_agentic_loop.py
python scripts/run_agentic_evals.py --output-json /tmp/opscat-agentic-evals.json --output-md /tmp/opscat-agentic-evals.md
bash scripts/verify.sh --profile full
```

Review release evidence in `docs/release-evidence.md` and the portfolio walkthrough in `docs/portfolio-demo.md`.
