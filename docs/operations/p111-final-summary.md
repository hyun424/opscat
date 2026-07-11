# P111 final summary: evidence-grounded RCA accuracy

## Scope

P111 improves diagnosis quality without granting the model action authority.
The NVIDIA model analyzes and cites the incident evidence; a deterministic
nearest-prototype prior, trained only on repetitions 1 and 2, contributes a
fault hypothesis. The final result remains advisory-only and is evaluated by a
separate scorer against hidden truth.

## Frozen blind protocol

- Official dataset: RCAEval RE1-OB.
- Development: repetition 1.
- Validation: repetition 2.
- Blind evaluation: repetition 3, 25 cases.
- Untouched reserve: repetition 4.
- Contaminated historical baseline: repetition 5; excluded from P111 selection.
- Freeze manifest SHA-256:
  `3bdb09f53128cd9d14e872e89b6e5fb4b336966cf68b0a10257e80a79c91c7d2`.
- Both provider output and deterministic synthesis output are preserved and
  replay-validated. Model, prompt, decoding settings, implementation, source,
  packets, and request envelope are bound by the freeze evidence.

## Blind results

| Metric | Paired P110 baseline | P111 | Delta |
| --- | ---: | ---: | ---: |
| Service Top-1 | 68% (17/25) | 80% (20/25) | +12 pp |
| Service Top-3 | 88% (22/25) | 96% (24/25) | +8 pp |
| Fault accuracy | 40% (10/25) | 84% (21/25) | +44 pp |
| Evidence validity | 100% | 100% | 0 pp |
| Unsafe-action counters | 0 | 0 | 0 |

Paired service Top-1 outcomes improved on four cases and regressed on one.
Fault classification improved on eleven cases and regressed on none.

The candidate Brier score improved from `0.4776` to `0.185344`; expected
calibration error improved from `0.552` to `0.1656`.

## Repeatability

A second live candidate run produced the same scored labels:

- service Top-1 agreement: 100%;
- fault-label agreement: 100%;
- joint agreement: 100%.

The provider's free-form evidence response is not claimed to be byte-identical;
only the scored service/fault decisions were identical across the two runs.

## Fault-level result

| Fault | Service Top-1 | Fault accuracy |
| --- | ---: | ---: |
| CPU | 80% | 80% |
| Delay | 80% | 100% |
| Disk | 100% | 100% |
| Loss | 40% | 40% |
| Memory | 100% | 100% |

## Release decision

`release_qualified=false`.

Passing gates include blind-role enforcement, freeze integrity, service Top-3,
overall fault accuracy, evidence validity, disk-fault floor, positive paired
deltas, zero unsafe-action counters, and repeat agreement.

Failing gates are:

1. service Top-1 is 80%, below the predeclared 84% target;
2. loss-fault accuracy is 40%, below the 60% floor;
3. no out-of-band cryptographic independent-review identity is configured.

An independent read-only verifier recomputed the freeze/source/packet hashes,
confirmed the reserve remained untouched, replayed all 25 baseline cases and
both 25-case P111 runs, and confirmed the metrics, calibration, agreement, and
safety counters. It also identified a historical P110 baseline limitation: the
baseline replay artifact binds its raw response, context, and cache key but does
not carry the P111-era `prompt_hash`, `system_prompt_sha256`, provider endpoint,
or provider API fields. This does not change the measured paired scores, but it
is a provenance gap and must be repaired in the next separately frozen phase.

The next accuracy phase must treat repetition 3 as consumed. It should improve
loss/service localization on new development evidence and must not score the
repetition-4 reserve until a new implementation and configuration are frozen.

## Evidence

- Freeze: `evals/real_datasets/external/p111/results/blind/freeze-manifest.json`
- Baseline: `evals/real_datasets/external/p111/results/blind/baseline/final/`
- Candidate runs: `evals/real_datasets/external/p111/results/blind/candidate-run1/final/`
  and `candidate-run2/final/`
- Paired comparison: `evals/real_datasets/external/p111/results/blind/final/comparison.json`
- Repeat agreement: `evals/real_datasets/external/p111/results/blind/final/repeat-agreement.json`
- Release gates: `evals/real_datasets/external/p111/results/blind/final/release.json`

Run the sealed local verification profile with:

```bash
bash scripts/verify.sh --profile p111-release
```
