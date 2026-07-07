# OpsCat P4 Ticket Roadmap — Eval/QA/Portfolio Gate

Status: active
Owner: leader + bounded specialist review when useful
Sequence rule: each ticket follows **plan -> plan check -> RED test -> GREEN implementation -> verification -> commit**.
Scope boundary: local/mock OpsCat only; no production credentials, no external mutations, no new dependencies unless explicitly justified and approved.

## P4 definition of done

OpsCat is portfolio-top-ready for the claim: "an agentic local on-call operator can safely monitor, diagnose, propose/execute approved actions, and produce evidence good enough to reduce human monitoring load." P4 is not the final SaaS launch; it is the evidence/QA layer that makes the claim credible.

Required release gates:
- Full local test suite passes.
- Static checks pass: ruff, mypy, compileall.
- Golden eval runner passes and writes JSON + Markdown artifacts.
- Dashboard has browser-contract E2E coverage for the operator journey.
- Connector failure behavior is represented in eval evidence, not only unit tests.
- Portfolio docs show scenario coverage, safety limitations, and remaining non-mock gaps.

## Ticket order

### P4-002 ✅ — Operator dashboard browser-contract E2E

Goal: prove the local operator dashboard is not just text-rendered but navigable and safe enough for demo usage.

Plan:
1. Add parser-based browser-contract E2E tests without a browser dependency.
2. Cover inbox -> detail navigation, required sections, report link, action approval instruction, and no mutation forms.
3. Cover HTML escaping for untrusted alert text.
4. Add stable `data-testid` hooks to server-rendered HTML so future browser tests can target the same contract.

Acceptance tests:
- `tests/test_operator_dashboard_e2e.py` fails before hooks exist.
- Targeted dashboard tests pass after implementation.
- Existing dashboard tests remain green.

Risks:
- Avoid Playwright dependency until a later explicit visual/browser phase.
- Do not add UI mutation forms; approval remains API/JSON only for safety.

### P4-003 ✅ — Connector failure eval expansion

Goal: make connector safety/failure behavior part of release evidence, not an invisible unit-test detail.

Plan:
1. Add deterministic connector eval runner or extend the existing eval runner with connector failure cases.
2. Cover missing credentials, timeout, malformed response, read-only contract violation, retry semantics, and audit/escalation recording.
3. Emit a JSON + Markdown report suitable for portfolio review.
4. Add the runner to `scripts/verify.sh`.

Acceptance tests:
- New connector eval tests fail before runner/report exists.
- Runner exits non-zero on failed connector checks.
- `scripts/verify.sh` includes connector eval evidence.

Risks:
- Keep all connector calls fake/local; no real Slack/GitHub/Sentry calls.

### P4-004 ✅ — Portfolio eval report artifact

Goal: turn raw eval outputs into a recruiter/interviewer-readable proof artifact.

Plan:
1. Add `docs/eval-report.md` or generated sample under `docs/operations/`.
2. Summarize golden scenarios, connector evals, safety gates, and known limitations.
3. Link commands that reproduce the evidence locally.
4. Update README with a short “Why this is agentic” evidence section.

Acceptance tests:
- Documentation checks assert required sections and commands exist.
- Eval report can be regenerated from scripts without manual edits.

Risks:
- Avoid overclaiming “human replacement”; phrase as local/mock operator replacement evidence.

### P4-005 ✅ — Golden corpus expansion and coverage taxonomy

Goal: broaden eval evidence beyond 23 happy/safety cases and show explicit coverage gaps.

Plan:
1. Add a coverage taxonomy file for incident classes, policy outcomes, escalation routes, redaction, connector failures, and night-autopilot conditions.
2. Expand or classify the golden corpus toward 50+ named scenarios if feasible without low-value duplicates.
3. Add tests that enforce metadata completeness and minimum category coverage.

Acceptance tests:
- Golden scenario metadata includes category, safety focus, and expected route.
- Corpus coverage tests enforce minimum counts per key category.
- Eval runner still passes all scenarios.

Risks:
- Prefer high-signal scenarios over artificial volume.

### P4-006 ✅ — Release evidence index and CI-ready gate

Goal: make one command prove the P4 release claim.

Plan:
1. Add a release evidence index document with exact commands and expected artifacts.
2. Ensure `scripts/verify.sh` produces or validates the eval artifacts.
3. Add smoke checks that output paths are deterministic and ignored/generated data is controlled.

Acceptance tests:
- `bash scripts/verify.sh` passes from a clean checkout with generated artifacts confined to intended paths.
- Docs mention all generated artifacts and verification commands.

Risks:
- Avoid committing noisy per-incident generated mock reports unless intentionally curated.

### P4-007 ✅ — P4 final hardening and review

Goal: close P4 with a reviewer-grade evidence pass.

Plan:
1. Run full verification: pytest, verify script, git diff review.
2. Fix flaky or under-specified assertions found during verification.
3. Produce final P4 completion note with changed files, evidence, and remaining product risks.

Acceptance tests:
- Full verification passes.
- Roadmap statuses reflect completed tickets.
- No known unexpected git changes remain.

Risks:
- P4 remains local/mock. Real production launch requires P5: auth hardening, persistence deployment, real connector OAuth/secrets, tenant admin UX, incident import integrations, and SOC2-style audit controls.

## Completion status

- P4-002: completed with browser-contract dashboard E2E and stable `data-testid` hooks.
- P4-003: completed with connector eval runner and verify gate integration.
- P4-004: completed with reviewer-facing eval report and README links.
- P4-005: completed with golden eval coverage taxonomy and gap policy.
- P4-006: completed with release evidence index and integration-verification links.
- P4-007: completed with `bash scripts/verify.sh` PASS on 2026-07-07 KST.
