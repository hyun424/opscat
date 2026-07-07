# OpsCat P18B Ticket Roadmap — Model Judgment Quality Lab

## Scope

P18B measures whether the LLM is actually good at incident judgment, independent from the P17 policy calibrator. P17 proved OpsCat can block unsafe model recommendations. P18B must quantify the model itself: raw route accuracy, hypothesis quality, evidence citation quality, missing-evidence behavior, action proposal quality, safety behavior, and calibration delta.

P18B uses P18A source-native snapshots and existing P10/P13/P14/P16/P17 infrastructure.

## Boundary

- No auth work: no OIDC, SSO, login, password auth, session UI, CSRF/session hardening, or production tenant provisioning.
- No production mutation: no Kubernetes/cloud/database mutation, no unrestricted shell, no real restart/rollback/scale/delete, and no customer credentials.
- Normal verification remains local/mock and does not call external model APIs.
- Live NVIDIA evaluation remains explicit opt-in via local `.env` and safe parser only; never `source .env`.
- P18B measures judgment quality; it does not introduce automatic production approval.

## Quality Questions

P18B answers:

1. How good is the model before policy calibration?
2. How much does P17 calibration improve final safety/route quality?
3. Where does the model fail: route, hypothesis, citation, evidence sufficiency, action proposal, or safety?
4. Does prompt hardening reduce over-aggressive `local_mock_auto_allowed` recommendations?
5. Does the model perform differently on seed cases versus P18A real-source snapshots?

## Tickets

### P18B-001 — Raw vs calibrated score split

Separate raw provider judgment scores from calibrated OpsCat scores.

Acceptance:
- Provider eval output includes `raw_provider_score`, `calibrated_score`, and `calibration_delta`.
- Raw route is scored against the rubric before P17 calibration.
- Existing calibrated scoring remains unchanged for safety evidence.

### P18B-002 — Judgment quality dimension expansion

Add model-quality dimensions beyond the current provider eval summary.

Acceptance:
- Dimensions include raw route, calibrated route, hypothesis, citation, required evidence, missing evidence, action proposal, forbidden action, and safety.
- Scores are JSON-serializable and documented.
- Existing P16/P17 behavior remains backward compatible.

### P18B-003 — Provider failure taxonomy

Classify why the model failed.

Acceptance:
- Failure labels include `route_over_auto`, `route_too_conservative`, `missing_evidence_ignored`, `hallucinated_citation`, `unsafe_action_allowed`, `weak_hypothesis`, `action_quality_low`, and `schema_or_parse_failure`.
- Each failed case reports one or more taxonomy labels.
- Taxonomy distinguishes model failure from policy-calibration correction.

### P18B-004 — P18A snapshot case selector

Convert P18A realtime replay snapshots into a model-quality evaluation set.

Acceptance:
- Can read `/tmp/opscat-realtime-real-cache-p18a.json` or any P18A replay JSON.
- Emits `JudgmentCase` records without requiring the original source files.
- Uses repo fixtures in normal verification and local `/private/tmp` cache when explicitly requested.

### P18B-005 — Prompt contract hardening v2

Tighten the LLM prompt to reduce over-aggressive automation.

Acceptance:
- Prompt explicitly forbids `local_mock_auto_allowed` unless evidence is sufficient, action is read-only, no missing evidence exists, and no rollback/restart/no-data ambiguity exists.
- Prompt tells the provider to mark rollback/restart/production-impacting actions as forbidden or approval/human required.
- Offline tests validate prompt text without live model calls.

### P18B-006 — Model quality report CLI

Add a CLI that runs model quality evaluation and emits reviewer-friendly JSON/Markdown.

Acceptance:
- CLI can run mock provider in normal verification.
- CLI can opt into NVIDIA with `--provider nvidia --env-file .env`.
- Report shows raw vs calibrated scores, failure taxonomy, calibration wins, and per-case details.

### P18B-007 — NVIDIA live regression evidence

Run opt-in NVIDIA quality eval on seed + P18A snapshot cases.

Acceptance:
- Output files stay in `/tmp`.
- Secret markers are absent from JSON/Markdown outputs.
- Evidence reports raw model score separately from calibrated OpsCat score.

### P18B-008 — Release evidence

Document P18B and update roadmap/release evidence.

Acceptance:
- Final summary maps P18B-001 through P18B-008 to artifacts.
- `scripts/verify.sh` includes bounded mock model-quality smoke.
- Full verification passes before closure.

## Execution Order

1. P18B-001 Raw vs calibrated score split
2. P18B-002 Judgment quality dimension expansion
3. P18B-003 Provider failure taxonomy
4. P18B-004 P18A snapshot case selector
5. P18B-005 Prompt contract hardening v2
6. P18B-006 Model quality report CLI
7. P18B-007 NVIDIA live regression evidence
8. P18B-008 Release evidence

## Final Gate

`bash scripts/verify.sh --profile full` must pass before P18B closure.
