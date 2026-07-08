# OpsCat P58 Ticket Roadmap — LLM Judgment Candidate Harness

P58 evaluates a local/mock LLM judgment lane under the same candidate and real-dataset gates built in P56-P57, establishing the harness needed before using external NVIDIA or other live model providers.

## Tickets

- P58-001 — Bridge prerequisite: consume P57 real-dataset candidate regression bridge results.
- P58-002 — Mock LLM evaluation: run local/mock LLM provider evaluation over seed judgment cases.
- P58-003 — LLM quality gates: require pass rate, overall score, citation/schema validity, and zero safety regressions.
- P58-004 — External-provider boundary: keep default verification on mock provider with no API call requirement.
- P58-005 — CLI report: write JSON and Markdown artifacts for local review.
- P58-006 — Verification integration: wire P58 smoke into `scripts/verify.sh`.
- P58-007 — Release evidence: document artifacts, boundaries, and final verification result.

## Acceptance criteria

- P57 bridge passes.
- Mock LLM provider evaluates at least four cases.
- Mock LLM pass rate is 1.0 and overall score is at least 0.9.
- Safety regressions and failed cases are empty.
- Action execution is disabled.
- Boundary remains offline/local with no default external model/API calls, live calls, production mutation, remediation execution, or unattended production-operation claim.
