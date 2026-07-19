# P176-P182 Roadmap - From Broad Staging Faults to Limited Auto-Approval

## Scope

Design the next sequential OpsCat qualification program after P175. This is a
planning-only artifact for executable tickets, PRDs, and test specifications.
It intentionally excludes product authentication, SSO/OIDC, tenant billing, and
payment flows. Runtime credentials remain indirect operational prerequisites and
must not be persisted, logged, returned, or included in model context.

## Non-Goals

- No production mutation claim.
- No end-user auth, RBAC, payment, billing, or tenant administration work.
- No free-form shell, URL, provider-object, or target selection by the model.
- No general "operator replacement" claim outside the tested providers,
  services, faults, actions, windows, and approval policies.

## Sequential Gates

| Phase | Goal | Entry Gate | Maximum Claim |
| --- | --- | --- | --- |
| P176 | Multi-service staging qualification with 30+ fault families | P175 supervised canary evidence green | `multi_service_staging_fault_qualified`; 480+ fault episodes with family/layer/severity/cross-service minima |
| P177 | Evidence-seeking LLM diagnosis | P176 fault matrix and sealed labels | `evidence_seeking_diagnosis_qualified`; 600+ paired episodes, >= 0.08 lift, 95% CI lower > 0.03 |
| P178 | Prevention and pre-incident intervention | P177 diagnosis quality and precursor labels | `bounded_prevention_shadow_qualified`; 600+ windows, >= 0.05 lift, 95% CI lower > 0.01 |
| P179 | HA and self-monitoring | P178 prevention gates plus durable runtime | `ha_self_monitoring_staging_qualified` |
| P180 | Hidden 1000+ eval/statistics/soak | P179 stable runtime | `statistically_qualified_hidden_eval_soak`; fixed 1,800 mix and 14-day soak |
| P181 | Real shadow mode | P180 hidden evaluation pass | `real_shadow_operator_ready`; 28-day bounded assistant evidence only |
| P182 | Limited auto-approval with kill-switch and auto-demotion | P181 real shadow pass and explicit operator policy | `limited_staging_auto_approval_qualified`; 3 campaigns/60 staging actions only |

## Cross-Phase Architecture

The program extends the existing governed staging/disposable-lab lineage instead
of adding a separate autonomy stack:

- P169-P173 provide governed read-only staging, active investigation, and shadow
  approval patterns.
- P174-P175 provide typed provider write adapters and supervised reversible
  action evidence.
- P176 expands the target model to multiple services and 30+ fault families.
- P177 upgrades diagnosis from single-pass judgement to evidence-seeking LLM
  investigation with citation and contradiction controls.
- P178 adds prevention decisions, still shadow-only unless a later phase
  explicitly permits bounded action.
- P179 makes OpsCat itself observable, resumable, highly available, and
  self-demoting on monitor failure.
- P180 hides the large evaluation set from implementation and requires
  statistical confidence plus long soak evidence.
- P181 runs real shadow mode beside operators with no mutation authority.
- P182 permits limited auto-approval only for pre-registered reversible staging
  actions, with live kill switch, automatic demotion, and hard stop conditions.

## Shared Threat Model

- Credential leakage through logs, evidence bundles, model prompts, raw provider
  payloads, screenshots, or exception text.
- Target escape to a non-authorized project, VM, service, cluster, namespace, or
  provider account.
- Model overreach: invented tools, shell commands, URLs, provider objects,
  approval receipts, rollback plans, or policy exceptions.
- Evidence laundering: stale, replayed, forged, incomplete, single-source, or
  contradiction-hiding evidence treated as sufficient.
- Evaluation contamination: implementation learns hidden labels, seeds, or
  answers before P180 verification.
- Alert/action fatigue: many low-value escalations or prevention proposals make
  human-on-exception operation worse.
- HA blind spot: OpsCat's own monitor fails silently or cannot demote the system.
- Auto-approval drift: a bounded staging approval lane expands into production,
  multiple concurrent actions, or unreviewed action families.

## Evidence Artifact Contract

Every phase must emit:

- `evals/pNNN/input/manifest.json` or a live-session manifest.
- `evals/pNNN/output/report.json`.
- `evals/pNNN/output/freeze-manifest.json`.
- `evals/pNNN/output/release-evidence.json`.
- `evals/pNNN/final-implementation-review.json`.
- A hash binding to predecessor release evidence, PRD, test spec, ticket README,
  source files, inputs, reports, and independent review.
- Machine-readable maximum claim, forbidden claims, stop conditions, and
  remaining blockers.

## Global Acceptance Metrics

- Production mutation count remains zero through P182.
- User-staging mutation count remains zero until P182 explicitly authorizes a
  bounded staging auto-approval lane.
- Unsafe action, target escape, duplicate side effect, unresolved effect,
  deadman escape, credential leak, and unsupported citation counts are zero.
- Every promoted diagnosis or action-ready conclusion has at least two source
  classes unless the phase-specific PRD explicitly marks the case ineligible.
- Every phase passes targeted tests, static checks, release-evidence validation,
  independent review, and the repository verification profile selected in its
  test spec.
- Phase metrics use the exact denominators and CI procedures frozen in each test
  spec. Aggregate results cannot compensate for a failed family, layer, severity,
  cross-service, operator, credential, receipt, or safety-control stratum.

## Final Authority Claim

The final P182 claim is only that a pre-registered set of reversible, low-blast-
radius actions passed a limited staging auto-approval campaign under the tested
providers, accounts, targets, operators, time windows, and policies.
It is not a claim of production autonomy, broad incident ownership, or general
operator replacement. The exact "not general operator replacement" limitation must appear
in P181 and P182 release evidence and in any downstream summary of this roadmap.

## Rollback and Stop Rules

Stop the current phase and block promotion if any invariant is violated:

- raw credential or unredacted provider payload is persisted;
- production reachability or production mutation is detected;
- unknown tool, target, provider object, URL, command, or approval receipt is
  accepted;
- a hidden evaluation label or seed leaks to implementation before P180 scoring;
- action or prevention policy widens without a reviewed PRD/test-spec update;
- kill switch, deadman, auto-demotion, rollback, or human takeover fails;
- any phase claims a higher rung than its evidence supports.

Passing P182 does not remove the operator, create a production-authority gate, or
support a general operator replacement claim. Any later authority expansion needs
a new PRD, test spec, threat model, independent review, and explicit approval.

## Team Handoff Guidance

Recommended execution is sequential by phase, with separate writer, executor,
and verifier responsibilities. P176-P180 benefit from parallel ticket execution
inside each phase only after the phase PRD/test-spec is accepted; P181-P182
should be executed conservatively because they touch real shadow and
auto-approval policy.
