# P13 Tickets — LLM Context Builder

P13 prepares OpsCat for LLM judgment without calling a model. It creates deterministic, redacted, prompt-injection-resistant context packets from incidents and judgment cases. Auth remains deferred and no model calls are introduced.

## Tickets

- [P13-001 — LLM Context Packet Schema](p13-001-llm-context-packet-schema.md)
- [P13-002 — Evidence Selector](p13-002-evidence-selector.md) — depends on P13-001
- [P13-003 — Unsafe Evidence Annotator](p13-003-unsafe-evidence-annotator.md) — depends on P13-002
- [P13-004 — Timeline Builder](p13-004-timeline-builder.md) — depends on P13-002
- [P13-005 — Candidate Hypothesis Context](p13-005-candidate-hypothesis-context.md) — depends on P13-001, P13-002
- [P13-006 — Runbook Context Selector](p13-006-runbook-context-selector.md) — depends on P13-005
- [P13-007 — Safety Constraint Pack](p13-007-safety-constraint-pack.md) — depends on P13-003
- [P13-008 — Required Output Schema](p13-008-required-output-schema.md) — depends on P13-001, P13-007
- [P13-009 — Context Builder CLI](p13-009-context-builder-cli.md) — depends on P13-001 through P13-008
- [P13-010 — Benchmark/Verification Integration](p13-010-benchmark-verification-integration.md) — depends on P13-009
- [P13-011 — P13 Release Evidence](p13-011-release-evidence.md) — depends on P13-001 through P13-010

## Boundary

No auth/session work, no model calls, no external API calls, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.

## Final Gate

`bash scripts/verify.sh --profile full` must pass before P13 closure.
