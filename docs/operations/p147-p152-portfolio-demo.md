# P147-P152 Portfolio Demo

This page describes the current P147-P152 portfolio-facing scope without
promoting the track beyond its evidence. It is a bounded local operator-agent
qualification path, not an auth system, production authority path, general
accuracy claim, or operator-replacement claim.

## Current Status

- The complete P147-P152 canonical artifact chain exists under `evals/p147`
  through `evals/p152`.
- Every phase includes `report.json`, `freeze-manifest.json`,
  `final-implementation-review.json`, and `release-evidence.json`.
- The final artifacts are rebound to the current source and predecessor files
  on every release-profile verification.
- P150 contains a completed real 7,200-cycle, one-second cadence monotonic
  wall-clock ledger, checkpoint, and result.
- Review history and limits are recorded in
  [`p147-p152-plan-review.md`](p147-p152-plan-review.md).

## What The Track Demonstrates

| Phase | Portfolio-facing scope | Boundary |
| --- | --- | --- |
| P147 | Durable offline provider-shaped shadow for Prometheus, Loki/JSONL, trace, Sentry-style, and deployment-history shapes. It persists cursor, heartbeat, dedupe, restart replay, deadman, redaction, and bounded read-only investigation state. | Canonical mode is offline/injected read-only evidence. It does not qualify credentials, live staging access, provider writes, or P134 OA3 live `HTTP_GET`. |
| P148 | Process-owned reversible lab actions with closed registry membership, pre-state hash, idempotency key, rollback snapshot, crash-safe receipt, and post-state verification. | No external model execution, shell action, credential use, staging mutation, or production mutation. |
| P149 | One-target canary control with SLO guards, maximum blast radius of one, kill switch, deterministic replay, and automatic rollback on harm, uncertainty, no-change, timeout, or contradiction. | Canary targets are process-owned lab targets only. |
| P150 | Accelerated seven-day deterministic fault replay plus a qualifying 7,200-cycle, one-second cadence wall-clock soak. The real soak binds monotonic-ns samples, append-only chain-linked JSONL ledger, checkpoint, raw file hashes, resource ceilings, and runner identity. | The two-hour soak is real local time. Accelerated replay alone cannot set `wall_clock_qualified=true`. |
| P151 | Sealed recorded-baseline mechanics: truth opens only after a truth-free prediction packet and pre-existing prediction/action commit are validated. | The canonical 48-row recorded fixture baseline qualifies sealing, scoring, and safety-gate mechanics. It does not prove fresh model accuracy or live-model performance. |
| P152 | Integrated local operator-agent gate with exact P146-P151 predecessor binding, kill switch, deadman escalation, rollback closure, and permission modes `manual`, `approve_once`, and `auto_safe_lab`. | Only `auto_safe_lab` can execute registry-bound process-owned lab actions. `approve_once` is local signed-fixture approval only while auth is deferred. |

## Explicit Non-Claims

- No authentication implementation.
- No production authority.
- No staging or production mutation.
- No unrestricted shell authority.
- No external messaging authority.
- No operator replacement.
- No general model-accuracy claim.
- No promotion from optional NVIDIA or real-provider reports into canonical
  release evidence.

## Reproducible Checks

Use a writable `uv` cache outside the home directory when running under a
restricted sandbox:

```bash
export UV_CACHE_DIR=/tmp/opscat-p147-p152-uv-cache
```

Verify every phase's tests, static checks, coverage threshold, and final
artifact reassembly:

```bash
for phase in p147 p148 p149 p150 p151 p152; do
  bash scripts/verify_p147_p152.sh "$phase"
done
```

Run the existing open-source packaging/security release gate separately:

```bash
bash scripts/verify.sh --profile p122-release
```

Run the real P150 wall-clock soak only when a two-hour local run is acceptable:

```bash
uv run --no-sync --extra dev python scripts/run_p150_qualification.py wall-clock --output-dir /tmp/opscat-p150-wall-clock
```

The P150 command is intentionally not a fast smoke. It must run 7,200
one-second cycles and write a qualifying ledger/checkpoint/result set before it
can support a wall-clock soak claim.

## Evidence Notes

- `scripts/verify_p147_p152.sh` validates the P146-to-P147 handoff and the
  sequential P147-P152 artifact chain one phase at a time.
- `bash scripts/verify.sh --profile p122-release` independently validates the
  open-source package, security, documentation, migration, soak, and clean
  install evidence.
- Current canonical denominators are P147 `8/8`, P148 `10/10`, P149 `8/8`,
  P150 `13/13`, P151 `48/48`, and P152 `8/8`.
- P150 reports `wall_clock_seconds=7200`, `wall_clock_cycles=7200`, and
  `wall_clock_qualified=true`.
- P152 intentionally reports
  `production_operator_replacement_ready=false`; the artifact proves a bounded
  local operator-agent gate, not unattended production authority.
- Missing, stale, reordered, forged, or companion-unbound final artifacts fail
  closed.
