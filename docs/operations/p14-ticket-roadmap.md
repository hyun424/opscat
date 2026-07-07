# OpsCat P14 Ticket Roadmap — LLM Judgment Adapter

## Requirements Summary

P14 attaches the first LLM-shaped judgment layer to the P13 context packet, but keeps execution local/mock and deterministic by default. The phase introduces a provider interface, a mock judgment provider, strict schema validation, evidence-citation checking, and a safety gate that prevents model text from becoming authority.

Boundary remains unchanged:

- no OIDC/SSO/login/password/session/CSRF browser auth work;
- no default external model/API calls and no network calls during normal verification;
- no real production mutation, Kubernetes/cloud/database execution, unrestricted shell, customer credentials, or hosted SaaS claims;
- no external dataset download during normal verification;
- LLM judgment is advisory and must pass schema, citation, and safety gates before downstream use.

## P14 Goal

Build an **LLM Judgment Adapter** where OpsCat can:

1. consume a P13 context packet;
2. produce a structured judgment through a mock provider;
3. validate required output schema;
4. verify evidence citations;
5. force unsafe/provider-invalid judgments into safe blocked/human-required routes;
6. expose CLI/report artifacts;
7. integrate a bounded smoke into verification.

## P14 Tickets

### P14-001 — LLM Judgment Provider Interface

**Outcome:** Implement llm judgment provider interface.

**Acceptance criteria:**

- Provider protocol supports deterministic mock provider and future opt-in provider adapters.
- Default provider is local/mock and performs no network calls.
- Provider output is plain JSON-compatible data.

### P14-002 — Judgment Response Schema

**Outcome:** Implement judgment response schema.

**Acceptance criteria:**

- Schema requires hypotheses, recommended_route, safe_actions, forbidden_actions_detected, missing_evidence, verification_plan, evidence_citations, and boundary.
- Allowed routes match OpsCat taxonomy.
- Invalid or missing fields fail closed.

### P14-003 — Mock LLM Judgment Provider

**Outcome:** Implement mock llm judgment provider.

**Acceptance criteria:**

- Mock provider consumes P13 context packets and returns deterministic judgment.
- Prompt-injection/unsafe evidence is surfaced as forbidden action evidence, not instructions.
- Mock output cites existing evidence IDs.

### P14-004 — Judgment Schema Validator

**Outcome:** Implement judgment schema validator.

**Acceptance criteria:**

- Validator rejects malformed JSON-like responses.
- Validator rejects invalid routes and malformed hypotheses/actions.
- Validator reports validation errors for CLI/reporting.

### P14-005 — Evidence Citation Checker

**Outcome:** Implement evidence citation checker.

**Acceptance criteria:**

- Every citation must reference an evidence ID present in the context packet.
- Unknown citations make the result invalid and blocked.
- Missing citations are reported as evidence errors.

### P14-006 — Judgment Safety Gate

**Outcome:** Implement judgment safety gate.

**Acceptance criteria:**

- Forbidden actions force blocked or human_required routes.
- Non-mock or production-like actions are removed from safe_actions.
- Safety gate emits deterministic gate reasons.

### P14-007 — Judgment Runner

**Outcome:** Implement judgment runner.

**Acceptance criteria:**

- Runner composes provider, schema validation, citation check, and safety gate.
- Runner returns raw judgment, validated judgment, gate status, and local/mock boundary.
- Runner never executes actions.

### P14-008 — LLM Judgment CLI

**Outcome:** Implement llm judgment cli.

**Acceptance criteria:**

- CLI accepts a P13 context packet or judgment cases/case-id input.
- CLI writes deterministic JSON and Markdown reports.
- CLI defaults to mock provider and performs no external calls.

### P14-009 — Prompt Injection Regression

**Outcome:** Implement prompt injection regression.

**Acceptance criteria:**

- Prompt/log injection fixture remains blocked or human_required.
- Unsafe production restart/kubectl instructions are reported as forbidden actions.
- No unrestricted shell/Kubernetes/cloud/database action is emitted as safe.

### P14-010 — Verification Integration

**Outcome:** Implement verification integration.

**Acceptance criteria:**

- scripts/verify.sh eval/full runs bounded LLM judgment smoke.
- Docs profile validates P14 release evidence.
- Smoke writes /tmp/opscat-llm-judgment-latest.md.

### P14-011 — P14 Release Evidence

**Outcome:** Implement p14 release evidence.

**Acceptance criteria:**

- Final summary maps P14-001 through P14-011 to code/tests/docs.
- Release evidence includes P14 commands and generated artifacts.
- ROADMAP records P14 implemented boundary and next phase.

## Execution Order

Tickets run sequentially using TDD: ticket commit, RED tests, implementation, verification, release evidence.
