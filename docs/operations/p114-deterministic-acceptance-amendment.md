# P114 deterministic acceptance amendment

## Timing and reason

This amendment is recorded before any RE2-OB labels are scored. Three
constrained NVIDIA adjudicators passed the minimal JSON safety contract but
failed the consumed-development nonnegative-delta and/or repeatability gates.
They are therefore removed from the authoritative diagnosis path rather than
being allowed to degrade it.

## Authoritative diagnosis

The P114 acceptance candidate is:

1. immutable RE2 evidence graph;
2. deterministic service localization;
3. service-name-free robust 3-NN fault classifier;
4. evidence-bound hypothesis output;
5. no action authority and no remediation execution.

The model artifact contains normalized feature vectors and fault labels only.
It contains no service names or case IDs. On leave-one-root-service-out RE2-SS
development evaluation it reached:

- service Top-1 85.56%;
- fault accuracy 73.33%;
- joint Top-1 65.56%;
- evaluation hash
  `sha256:c259256a107d1de5e6c7ec55fd3e430d11db8b8a4b6f06a7e2e938ed1a33ce90`;
- full development model hash
  `sha256:b92e74fdfdccdc60c6208d45a9a7fb3c4bb2786d9d7a96044c0ab391850480d9`.

## Predeclared RE2-OB gates

- service Top-1 at least 0.60 and Top-3 at least 0.80;
- fault accuracy at least 0.60 and every fault at least 0.45;
- joint service/fault Top-1 at least 0.50;
- joint candidate recall at least 0.75 and evidence precision at least 0.95;
- replay consistency and diagnosis preservation exactly 1.0;
- all truth-leak, action, credential, shell, write, adapter, and mutation
  counters exactly zero.

The LLM adjudicator remains an experimental development artifact. It cannot
affect blind predictions, acceptance, release evidence, or actions. This is a
scope reduction after a negative development result, not a lowered accuracy or
safety threshold.
