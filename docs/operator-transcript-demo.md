# OpsCat Operator Transcript Demo

This is the best quick demo for reviewers who want to see agentic incident-response behavior without production risk. It shows agentic reasoning with evidence but no production action: observe signals, form suspicions, choose tools, inspect evidence, compare hypotheses, decide safely, draft a non-executing remediation or handoff, verify the local/mock outcome, report, and identify improvement gaps.

Run it locally:

```bash
uv run --no-sync --extra dev python scripts/run_operator_transcript_demo.py
```

Expected smoke line:

```text
scenarios=4 transcript_steps>=40 hypotheses>=12 executions=0 recovery_proven=1 blocked=2 human_gated=1
```

## Scenarios

- Payment deploy regression -> safe rollback PR draft / local_mock_recovery_proven.
- DB connection pool saturation -> human-gated scale/connection-pool handoff / recovery_not_proven.
- Noisy metric spike with missing evidence -> blocked_more_evidence_needed.
- Prompt-injection-like log content -> blocked_safety_guardrail.

## Boundary

P94 is local/mock-only and not production autonomy. It performs no auth work, live API calls, credential reads, network calls, production mutation, real remediation/action execution, or external model/API calls. It does not claim executed rollback, executed scale-up, live provider recovery verification, or credentialed operation.
