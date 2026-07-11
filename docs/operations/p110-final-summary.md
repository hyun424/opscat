# P110 Final Summary — Labeled Real-Data LLM Diagnosis

## What changed

P110 is the first OpsCat phase that scores an external LLM against hidden,
official root-cause labels instead of authored fixtures or unlabeled telemetry.

- Imported all 125 RCAEval RE1-OB incidents from the pinned official archive.
- Selected repetition 5 as a balanced 25-case holdout (five services × five
  fault families).
- Replaced label-bearing case paths with per-installation HMAC identifiers.
- Converted raw time series into bounded pre/post/delta evidence with stable
  source-bound citation IDs.
- Sent only sealed candidate packets to NVIDIA Nemotron; scorer truth remained
  in a separate in-process envelope.
- Recomputed metrics from raw predictions and hidden labels; candidate-submitted
  scores are not trusted.
- Never executed advisory actions.

## Real NVIDIA result (locally verified, hard release fail-closed)

Model: `nvidia/nemotron-3-ultra-550b-a55b`

Two adversarial reviews rejected weaker release paths. P110-010 now seals truth,
binds every packet/cache/config, preserves each raw provider response, verifies
its hash, and replays strict parsing during merge. Local verification can still
be self-authored, so it is not treated as cryptographic proof of reviewer
identity or live provider execution. Hard release therefore remains false.

| Metric | Result | 95% bootstrap interval |
| --- | ---: | ---: |
| Root service Top-1 | 20/25 = **80%** | 64–92% |
| Root service Top-3 | 23/25 = **92%** | 80–100% |
| Fault-family accuracy | 13/25 = **52%** | 32–72% |
| Evidence citation precision | 140/140 = **100%** | 100–100% |
| Abstention rate | 0/25 = **0%** | 0–0% |
| Harmful advisory-action rate | 0/25 = **0%** | 0–0% |
| Mean model latency | **68.67 s/case** | 54.32–84.72 s |

Fault-family accuracy exposes the main weakness: CPU 100%, delay 80%, memory
80%, disk 0%, and loss 0%. Service localization is already useful, but the
model currently confuses disk/loss symptoms with other fault families. OpsCat
must not market this result as operator replacement.

## Safety result

- Truth leaks: 0
- Invalid/invented citations: 0
- Provider failures in the final 25 cases: 0
- Harmful advisory actions: 0
- Executed actions: 0

## Independent verification

- Official archive SHA-256/MD5/size recomputed and matched the pinned manifest.
- A fresh temporary merge reproduced the final candidate, evaluation, and
  artifact-hash files byte-for-byte.
- Eight forged provenance/release probes were rejected.
- P110 suite: 59 passed; full fast suite, Ruff, and mypy passed.
- Review artifact: `evals/real_datasets/external/p110/results/final/independent-review.json`.
- Final `release-nvidia.json`: all data/quality/safety/hash gates true;
  `release_qualified=false` only because cryptographic independent-review
  authentication is not configured.

## Commands

```bash
.venv/bin/python scripts/acquire_p110_rcaeval.py --allow-network
.venv/bin/python scripts/run_p110_labeled_benchmark.py --mode nvidia --max-cases 25 --max-calls 25
bash scripts/verify.sh --profile p110-release
```

The actual run used five isolated five-case batches and
`scripts/merge_p110_labeled_batches.py` so provider latency did not force a
fully sequential benchmark.

## Honest limits

RE1-OB is metric-only, covers one microservice system, uses injected faults,
and has only one held-out repetition per service/fault cell. Evidence precision
proves citations exist in the packet; it does not yet prove that every cited
feature causally supports the diagnosis. Repeated-run stability is not yet
measured. Multi-source RE2/RE3, counterfactual remediation quality, calibration,
and real production shadow traffic remain future gates.
