# P111 plan review

## Initial verdict: rejected

The adversarial reviewer rejected an unconstrained “improve accuracy” pass
because the known P110 repetition-5 failures could be prompt-tuned, producing a
false holdout gain. The initial proposal also lacked calibration, repeatability,
paired-baseline, and release-attestation gates.

## Revisions

- Classified repetition 5 as contaminated development evidence.
- Allocated repetitions 1/2/3/4 to development/validation/blind/reserve roles.
- Added a configuration freeze before blind scoring.
- Added paired baselines, per-fault floors, calibration, repeated-run, safety,
  and cryptographic release gates.
- Kept the candidate schema, scorer separation, raw-response replay, and
  advisory-only authority invariant.

## Implementation readiness

The architecture review accepted an additive P111 wrapper over P110. Derived
diagnostic views are deterministic transformations of candidate-visible
evidence; P110 packet construction, scoring, replay, and release artifacts stay
unchanged. P111 stage inputs, raw outputs, hashes, and deterministic synthesis
must be independently replayable. Implementation is ready under these bounds.
