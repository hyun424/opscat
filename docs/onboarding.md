# OpsCat Customer Onboarding Draft

This is the paid-beta onboarding shape OpsCat should support once the local MVP is green and real connector work begins. The current repository remains local/mock-only.

## 5-minute local demo

1. Clone the repository.
2. Create a Python virtual environment.
3. Install development dependencies.
4. Run the deterministic demo.
5. Inspect the generated incident report and safety boundaries.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python scripts/demo.py
```

Current caveat: this command is blocked in the latest inspected head by `app/models/action.py` indentation syntax error. See `integration-verification.md`.

## Paid-beta setup checklist

Before a real customer connects OpsCat, require:

- tenant/workspace creation;
- tenant-scoped authentication and authorization;
- encrypted integration token storage;
- connector deployment location selected by the customer;
- explicit capability grants per integration;
- service/environment mapping;
- runbook registration;
- escalation contacts and quiet-hours policy;
- approval policy for each action class;
- redaction policy and test sample;
- incident report retention policy.

## Permission explanation

OpsCat should request narrow capabilities, never broad admin tokens.

| Capability | Why OpsCat needs it | Default |
| --- | --- | --- |
| `sentry:issues:read` | Fetch incident issue details and event fingerprints. | Read-only |
| `github:commits:read` | Correlate deploys and commits with incident onset. | Read-only |
| `github:pull_requests:write` | Draft rollback/remediation PRs after approval. | Approval required |
| `slack:messages:write` | Send incident summaries and wake-up packets. | Approval or policy-gated |
| `kubernetes:pods:read` | Inspect runtime state in future connector mode. | Read-only |

## What OpsCat will not do by default

- Execute arbitrary shell commands.
- Mutate production infrastructure.
- Access secrets unless a connector capability explicitly permits it.
- Bulk-copy raw logs into OpsCat Cloud.
- Retry actions indefinitely.
- Suppress escalation when verification fails.

## First paid-beta success criteria

- Known low-risk incidents can be auto-handled or approval-gated.
- Unknown, high-risk, or unverified incidents wake humans with evidence.
- Every action has actor, policy decision, payload/diff, timestamp, and post-check outcome.
- Morning reports summarize what happened overnight.
- Customers can explain exactly what data left their environment.
