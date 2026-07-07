# OpsCat P19 Ticket Roadmap — Operator Judgment Improvement Loop

## Scope

P19 turns P18B model-quality results into an operator-grade improvement loop. P18B can measure model failures. P19 must convert those failures into safe, auditable improvement proposals and regression packs without automatically changing production behavior.

The goal is to move from "LLM judged an incident" to "OpsCat can inspect its own judgment failures, ask for missing evidence, propose safer prompt/policy/test updates, and prove whether the next run improved."

## Boundary

- No auth work: no OIDC, SSO, login, password auth, session UI, CSRF/session hardening, or production tenant provisioning.
- No production mutation: no Kubernetes/cloud/database mutation, no unrestricted shell, no real restart/rollback/scale/delete, and no customer credentials.
- Normal verification remains local/mock and does not call external model APIs.
- Live NVIDIA evaluation remains explicit opt-in via local `.env` and safe parser only; never `source .env`.
- P19 generates improvement proposals and regression packs; it does not self-edit prompts/policies without tests and commits.
- P19 does not claim unattended production operation.

## Quality Questions

P19 answers:

1. Given a model-quality report, which failures should be fixed first?
2. What exact prompt/policy/rubric/test improvement should be proposed for each failure?
3. What missing evidence should the agent fetch before asking for approval or action?
4. Can the system produce a regression pack from failures so future model changes cannot silently regress?
5. Can operators see whether improvement proposals reduced raw failures without hiding safety corrections?

## Tickets

### P19-001 — Failure intake and priority model

Read P18B model-quality JSON and normalize failures into prioritized improvement candidates.

Acceptance:
- Loads P18B JSON reports from mock or NVIDIA runs.
- Groups failures by taxonomy label, case, provider, and affected dimensions.
- Produces deterministic priorities: safety > over-auto > missing evidence > citation > hypothesis/action quality.
- Keeps raw model failure separate from policy-calibration correction.

### P19-002 — Improvement recommendation engine

Map failure labels to concrete non-mutating recommendations.

Acceptance:
- `unsafe_action_allowed` proposes prompt and policy allowlist tightening.
- `route_over_auto` proposes stricter auto-route preconditions.
- `missing_evidence_ignored` proposes evidence-fetch questions/tool calls.
- `hallucinated_citation` proposes citation contract/test additions.
- Output includes owner area, rationale, expected effect, and verification command.

### P19-003 — Missing evidence plan builder

Generate the next safe read-only evidence requests for each weak case.

Acceptance:
- Emits only read-only local/mock tools such as log search, metric query, trace fetch, service health, recent deploy lookup.
- Blocks restart/rollback/shell/database/cloud/Kubernetes actions.
- Explains why each evidence request is needed.

### P19-004 — Regression pack generator

Convert failed cases into a local regression pack.

Acceptance:
- Writes a JSON pack with selected cases, failure labels, expected improvements, and no secrets.
- Can be used by future eval runs without live provider calls.
- Preserves case IDs and citation requirements.

### P19-005 — Improvement loop report CLI

Add a CLI that reads P18B output and writes a reviewer-friendly JSON/Markdown plan.

Acceptance:
- Normal verification uses a repo fixture, not live NVIDIA.
- CLI supports `/tmp/opscat-nvidia-model-quality-p18b.json` when explicitly provided.
- Report shows top failures, recommendations, missing-evidence plans, and regression pack path.

### P19-006 — Improvement trend comparator

Compare before/after model-quality reports.

Acceptance:
- Shows raw score delta, calibrated score delta, taxonomy deltas, and newly introduced safety failures.
- Fails closed if reports are incompatible.
- Does not treat policy-calibration wins as raw model improvement.

### P19-007 — Verification integration

Add bounded mock improvement-loop smoke to `scripts/verify.sh`.

Acceptance:
- Smoke creates a small local P18B-like report fixture and runs the improvement CLI.
- Full verification remains offline/local/mock.
- Generated output stays in `/tmp` or verify temp dir.

### P19-008 — Release evidence

Document P19 and update roadmap/release evidence.

Acceptance:
- Final summary maps P19-001 through P19-008 to artifacts.
- `docs/release-evidence.md` includes P19 evidence and verification commands.
- Full verification passes before closure.

## Execution Order

1. P19-001 Failure intake and priority model
2. P19-002 Improvement recommendation engine
3. P19-003 Missing evidence plan builder
4. P19-004 Regression pack generator
5. P19-005 Improvement loop report CLI
6. P19-006 Improvement trend comparator
7. P19-007 Verification integration
8. P19-008 Release evidence

## Final Gate

`bash scripts/verify.sh --profile full` must pass before P19 closure.
