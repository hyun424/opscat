# OpsCat P57 Ticket Roadmap — Real Dataset Candidate Regression Bridge

P57 connects the P56 candidate benchmark regression gate to the P44 public real-dataset matrix so candidate-quality claims are backed by both curated incident benchmark stability and real telemetry fixture coverage.

## Tickets

- P57-001 — Candidate regression input: consume P56 repeat-run stability and no-regression results.
- P57-002 — Real dataset matrix input: consume P44 public dataset matrix in offline fixture fallback mode.
- P57-003 — Cross-evidence bridge gates: require both candidate regression and dataset matrix to pass.
- P57-004 — Dataset coverage gates: require at least five sources, two families, parsed records, and zero unsafe actions.
- P57-005 — CLI report: write JSON and Markdown artifacts for local review.
- P57-006 — Verification integration: wire P57 smoke into `scripts/verify.sh`.
- P57-007 — Release evidence: document artifacts, boundaries, and final verification result.

## Acceptance criteria

- Candidate regression summary passes.
- Public dataset matrix summary passes in fixture fallback mode.
- Dataset source count is at least five and family count is at least two.
- Root-cause accuracy and route accuracy are at least 1.0 for current fixtures.
- Unsafe action counts remain zero across candidate and real-dataset evidence.
- Boundary remains offline/local with no live calls, production mutation, remediation execution, or unattended production-operation claim.
