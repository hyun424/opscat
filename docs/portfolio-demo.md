# OpsCat Portfolio Demo Package

## Problem

On-call teams need an assistant that can do more than summarize logs: it must preserve evidence, choose bounded actions, refuse unsafe mutations, verify recovery, and leave an audit trail.

## Agentic loop

OpsCat demonstrates the local/mock loop **observe → correlate → diagnose → plan → risk → act → verify**.

Run it in under five minutes:

```bash
make install
python scripts/demo_agentic_loop.py
python scripts/run_agentic_evals.py --output-json /tmp/opscat-agentic-evals.json --output-md /tmp/opscat-agentic-evals.md
```

## Architecture

```text
alerts/connectors -> incident services -> evidence/root cause -> runbook plan -> policy/risk -> mock action -> verification/report
```

## Safety model

- local/mock by default;
- no production credentials;
- no live provider mutation;
- dangerous action attempts must be blocked in evals;
- auth remains deferred, so this is not production-ready.

## Evidence

- `scripts/run_agentic_evals.py` scores correlation, root cause, runbook, risk, unsafe blocking, and recovery verification.
- `scripts/demo_agentic_loop.py` prints the seven-stage reviewer transcript.
- `docs/security-review-p6.md` documents P6 threats and gaps.
- `docs/release-evidence.md` links the reproducible commands and artifacts.
