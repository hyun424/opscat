# OpsCat Portfolio Summary

OpsCat is an agentic AI on-call system for incident response automation. It is designed to show production-minded agent engineering, not chatbot prompting.

## One-line pitch

OpsCat handles routine incident first response and wakes humans only on exception: high risk, low confidence, failed verification, protected domains, or policy-denied actions.

## What it demonstrates

- Tool-using agent workflow over incident context.
- Deterministic incident state machine and timeline.
- Evidence-backed hypotheses with source IDs.
- Policy/risk engine separating model recommendation from execution authority.
- Approval-gated actions inspired by Codex-style tool execution UX.
- Human-on-exception operations model: detect, classify, investigate, act, verify, escalate.
- Night Autopilot concept for safe quiet-hours remediation with bounded attempts and morning reports.
- Evaluation scenarios and safety regression tests.
- Audit-friendly incident reports and wake-up packets.

## Why it matters

Real-world agentic AI systems need more than LLM calls. They need permissions, guardrails, tenant boundaries, state, verifiable actions, rollback thinking, human approval, data minimization, and observability of the agent itself. OpsCat is built around those constraints.

## Paid-beta framing

OpsCat is not production-ready yet, but the documentation now defines the paid-beta bar clearly: tenant-scoped auth, encrypted integration tokens, connector deployment, idempotent webhook/action handling, redaction tests, and a first customer-facing onboarding path. The current local MVP remains mock-only and explicitly documents blockers in `integration-verification.md`.
