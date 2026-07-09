# OpsCat P94 Ticket Roadmap — Operator Transcript Demo / Human-like Incident Response Walkthrough

P94 adds a deterministic reviewer-friendly local/mock transcript demo. It improves the product demo quality by making OpsCat read like an experienced incident responder rather than a static evidence bundle.

Boundary: no auth work, no live APIs, no credentials, no network, no production mutation, no real remediation/action execution, no external model/API calls, and no production autonomy claim.

- P94-001 — Transcript schema: define transcript ID, scenario ID, title, operator goal, transcript steps, hypotheses, tool plan, decision, verification, report summary, safety boundaries, forbidden claims, and zero side-effect counters.
- P94-002 — Four local/mock scenarios: cover payment deploy regression, DB pool saturation, noisy metric spike with missing evidence, and prompt-injection-like log content.
- P94-003 — Human-like reasoning steps: require observe, suspect, choose tools, inspect evidence, compare hypotheses, decide safely, draft handoff, verify, report, and improve phases.
- P94-004 — One-command CLI artifact: generate JSON and Markdown outputs with count-style smoke evidence.
- P94-005 — Reviewer docs: document why this is the best quick demo for reviewers and preserve the local/mock boundary.
- P94-006 — Verification integration: wire P94 smoke and docs contract tests into `scripts/verify.sh`.
- P94-007 — Release evidence closure: update release evidence, roadmap, portfolio links, and final summary without claiming production autonomy.
