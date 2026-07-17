# P169-P173: Governed Read-Only Staging Program

This program moves OpsCat from disposable-lab qualification to governed
human-on-exception staging evidence without granting production authority.
P169-P173 prove real read-only attachment, real elapsed endurance, blinded
judgment quality, active evidence investigation, and counterfactual approval
quality.

| Phase | Capability | Maximum qualified claim |
| --- | --- | --- |
| P169 | Governed read-only staging telemetry attachment | Read-only staging attachment ready, or observed only after real owner-approved reads |
| P170 | 24-hour real wall-clock shadow soak | Read-only staging shadow endurance |
| P171 | Blinded staging judgment benchmark | Informational point estimate, or confidence-bound benchmark when sample gates pass |
| P172 | Active evidence investigation in staging | Bounded read-only investigation utility |
| P173 | Shadow approval and counterfactual action evaluation | Counterfactual fixed-action policy quality |

## Ordered phase contracts

| Phase | Canonical predecessor | Required predecessor status | Release status |
| --- | --- | --- | --- |
| P169 | canonical P168 release evidence | `p168_accelerated_unattended_lab_soak_qualified` | governed attachment runtime ready; live observation is a separate promotion gate |
| P170 | canonical P169 readiness evidence | P169 runtime ready | wall-clock soak runtime ready; 24-hour completion is a separate promotion gate |
| P171 | canonical P170 readiness evidence | P170 runtime ready | blinded staging benchmark ready; confidence-bound promotion remains data-gated |
| P172 | canonical P171 evidence | P171 informational or confidence-bound benchmark readiness | active read-only investigation ready |
| P173 | canonical P172 evidence | P172 active investigation ready | counterfactual shadow approval qualified |

P169 may qualify readiness from recorded transport, but observed attachment
requires target-owner approval, live acknowledgement, indirect scoped credential
reference, and `real_network_call_count > 0`.

P170-P173 may be implemented and release-chained as bounded readiness or
counterfactual evidence. They must not promote to live endurance, real staging
quality, or live action claims until the separately generated P169 observed and
P170 24-hour artifacts exist.

## Safety invariants

- Production mutations remain disabled.
- P169-P173 are read-only or counterfactual; action execution, staging mutation,
  production mutation, and real approval/action counts remain exactly zero.
- Runtime connector secrets are indirect references only. Raw secrets are never
  persisted, logged, returned, or included in model context.
- Missing, stale, conflicting, unavailable, or insufficient evidence produces
  `investigate_more`, `abstain`, or `human_required`.
- The model may select hypotheses and bounded read-only evidence tools only. It
  may not invent tools, mint approvals, widen capabilities, or execute commands.
- Every retained evidence item records source, observed time, collection time,
  content hash, and redaction metadata.

## Phase-specific gates

### P169 attachment gates

- GET-only transport, exact host/path allowlists, HTTPS, timeout, redirect,
  production-label, response-size, credential, and raw-response gates fail
  closed.
- At least three read-only source classes and two independent providers are
  observed for `p169_live_attachment_observed`.
- Every network read has a P169-owned immutable receipt in an append-only
  per-request hash chain. P153 aggregate audit counters are not equivalent.
- Reports separate readiness from observed attachment and keep write/action/
  mutation/shell/external-model counters at zero.

### P170 endurance gates

- `wall_clock_24h_completed=true` is derived from signed UTC start/end receipts
  plus per-process monotonic segments with boot/session IDs.
- Poll interval, expected source denominator, outage taxonomy, and resource
  ceilings are frozen before `start`.
- Polling success is at least 99.9%; real provider failures stay in the frozen
  denominator unless separately signed external outage or injection evidence
  justifies classification.
- Restart/resume completes within 60 seconds with no duplicate evidence,
  actions, or skipped ledger generations.

### P171 benchmark gates

- Fewer than 30 labeled staging incident/precursor episodes or fewer than 200
  healthy windows can produce only an informational point-estimate report.
- Confidence-bound promotion requires a separately pre-registered sample size
  sufficient for requested one-sided 95% bounds, including at least 300 healthy
  windows for a zero-observed-false-alert 1% upper-bound claim.
- Root-cause, precursor, citation, calibration, selective accuracy, abstention,
  OOD, and family-specific metrics are reported without hiding failed families.

### P172 investigation gates

- Tool capability registry entries must be backed by providers actually
  observed in the canonical P169 attachment.
- Configured-but-unobserved, unknown, or unavailable providers cannot satisfy
  evidence requirements.
- Action-ready conclusions require at least two independent source classes.
- Each episode is limited to eight read-only tool calls and one bounded model
  deliberation budget; exhaustion fails closed.

### P173 counterfactual gates

- Shadow evaluation never calls a reversible action controller and never emits
  an executable `approved` receipt.
- Eligible outcomes use `would_approve_not_authorized` and increment
  `counterfactual_would_approve_count`, not `auto_approval_count`.
- Action execution, auto-approval, staging mutation, production mutation, and
  real provider actions remain exactly zero.
- Denials identify the failed evidence, policy, capability, freshness, or
  authority requirement.

## Release blockers after P173

- provider-adapter write sandbox qualification;
- explicit authorization checkpoint for any real staging mutation;
- production auth/OIDC/SSO and tenant authorization;
- independent security, privacy, and operational acceptance review;
- supervised production canary evidence before any production-autonomy claim.
