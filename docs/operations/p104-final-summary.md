# P104 Final Summary - Evidence Gap Investigator

## Delivered

- Shared decision envelope for evidence-gap routing across `inspect_next`,
  `sufficient_for_policy_handoff`, `escalate_gap`, and fail-closed abstention.
- Evidence requirement contract and evidence state model covering supporting,
  contradicting, absent, stale, unavailable, distracting, duplicate, and
  not-yet-queried states.
- Deterministic sufficiency hard gates that require fresh critical evidence,
  no unresolved contradiction, adequate telemetry, no unavailable critical
  capability, and explicit citations before policy handoff.
- Information-value next-tool selection over the closed P101 read-only catalog.
- Optional strict LLM gap proposal path that remains advisory and cannot declare
  sufficiency, add tools, request credentials, authorize action, or override
  deterministic gates.
- Exact escalation payloads for missing, contradicted, stale, unavailable, and
  redacted evidence gaps.
- Network-free CLI and benchmark reports through
  `scripts/run_evidence_gap_investigator.py`.

## Benchmark evidence

The P104 CLI benchmark was run on the full committed P104 fixture:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev python scripts/run_evidence_gap_investigator.py \
  --max-cases 10 --sample-size 10 --seeds 11,29,47 \
  --output-json /tmp/opscat-p104-evidence-gap-investigator-full.json \
  --output-md /tmp/opscat-p104-evidence-gap-investigator-full.md
```

Measured result:

- Cases: **10** committed fixture cases from
  `evals/evidence_gap/seed/scenarios.json`.
- Arms: **p104**, **p103**, **p101**, **fixed_tool**, and **control**.
- Rows: **150** comparison rows.
- Execution valid: **true**.
- Default network calls: **0**.
- Default model calls: **0**; `include_nvidia=false` and
  `network_enabled=false`.
- P104 false-remediation handoff rate: **0.0**.
- P103 false-remediation handoff rate in the equal-state comparison: **0.4**.
- P101 false-remediation handoff rate in the equal-state comparison: **0.35**.
- Fixed-tool false-remediation handoff rate: **0.5**.
- Valid-case recovery retention delta, P104 versus P103: **0.0**.
- The benchmark distinguishes **valid absence** from **unavailable** telemetry.

## Safety counters

- `action_authority=false`.
- No auth.
- No production mutation.
- No mutating diagnostics.
- Default network calls: 0.
- Default model calls: 0.
- Provider action execution count: 0.
- Production mutation count: 0.
- Scorer leakage count: 0.
- Repeated tool count: 0.
- Mutating diagnostic count: 0.
- Unknown tool count: 0.
- State mismatch count: 0.

## Boundaries

P104 is an evidence-sufficiency and gap-reporting layer, not production
autonomy. It does not prove production diagnosis quality, remediation
effectiveness, connector correctness, unattended production operation, or
operator replacement. It adds no auth, no production mutation, no provider action
authority, and no default external calls. Optional live-provider use remains
explicit opt-in, bounded, network-enabled by flag, and advisory-only.

## Verification anchors

- `app/services/evidence_gap_investigator.py`
- `scripts/run_evidence_gap_investigator.py`
- `evals/evidence_gap/seed/scenarios.json`
- `tests/test_evidence_gap_investigator.py`
- `tests/test_p104_release_evidence.py`
- `docs/operations/p104-ticket-roadmap.md`
- `docs/operations/p104-plan-review.md`

The release integration wires `evidence_gap_investigator_smoke` into
`scripts/verify.sh` and adds `tests/test_p104_release_evidence.py` to the docs
contract profile.
