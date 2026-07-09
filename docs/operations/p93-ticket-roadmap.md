# OpsCat P93 Ticket Roadmap — Portfolio Demo Narrative & Operator Walkthrough Evidence

P93 turns the P92 local/mock acceptance result and selected prior evidence into a reviewer-facing portfolio demo pack. It makes the evidence accessible through a one-command artifact, operator walkthrough, README polish, architecture narrative, release evidence, and docs-profile verification.

Boundary: no auth work, no live APIs, no credentials, no network, no production mutation, no real remediation/action execution, no external model/API calls, and no production autonomy claim.

- P93-001 — Portfolio demo pack schema: define demo ID, pitch, role signals, architecture sections, walkthrough steps, proof points, safety boundaries, forbidden claims, demo commands, expected outputs, readiness status, remaining gaps, and zero side-effect counters.
- P93-002 — Deterministic fixture pack: encode the P92-backed local/mock portfolio story in `evals/actions/p93_portfolio_demo_pack.json`.
- P93-003 — One-command CLI artifact: generate JSON and Markdown outputs with count-style smoke evidence.
- P93-004 — Operator walkthrough docs: document observe, correlate, investigate, decide, draft, act safely, verify, report, and improve stages.
- P93-005 — README and architecture polish: place the portfolio story, quick demo command, evidence links, and local/mock boundary near the top.
- P93-006 — Verification integration: wire P93 smoke and docs contract tests into `scripts/verify.sh`.
- P93-007 — Release evidence closure: update release evidence, roadmap, and final summary without claiming production autonomy.
