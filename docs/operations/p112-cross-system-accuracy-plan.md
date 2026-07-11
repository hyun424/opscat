# P112 cross-system RCA accuracy plan

## Objective

Raise generalizable root-service localization and `loss` versus `delay`
classification without tuning on the consumed P111 blind split or weakening
the advisory-only safety boundary.

## Why P112 is required

P111 improved the repetition-3 paired baseline, but release remained closed:

- service Top-1: `0.80`, below the predeclared `0.84` target;
- loss accuracy: `0.40`, below the predeclared `0.60` floor;
- P111 made three loss/delay mistakes and three service-localization mistakes;
- the historical P110 paired baseline lacks P111-era request-envelope fields.

The P111 blind labels are now consumed. They may be used only as a frozen
regression report, never for P112 feature, threshold, or model selection.

## Data governance

### Development system

Use official RCAEval `RE1-SS` (Sock Shop), pinned to the Zenodo record and local
SHA-256. It has the same five fault families but a different service topology,
so improvements must be service-name independent.

- repetitions 1-3: training;
- repetition 4: validation and one-time configuration selection;
- repetition 5: contaminated development evidence. During the initial
  implementation experiment it was evaluated across more than one candidate
  weight, so it cannot serve as confirmation or release evidence.

### Final blind system

Use only RCAEval `RE1-OB` repetition 4 for final blind acceptance. It remains
unscored until the P112 implementation, configuration, P111 paired baseline,
candidate packets, request envelopes, and acceptance gates are frozen.

RE1-OB repetitions 1-3 are consumed development data. They may join the final
training fit only after feature schema and pair weight are selected on RE1-SS;
they cannot alter the selected schema, weight, thresholds, or gates. Repetition
5 remains a frozen contaminated diagnostic report and is not used for final
training or selection. RE1-TT, RE2, and RE3 remain future confirmation sets.

## Design

1. Generalize archive loading and provenance validation across pinned RE1
   systems without relaxing path, size, checksum, case-count, or label checks.
2. Replace service-name-position prototypes with service-agnostic candidate
   hypotheses. Score every visible service/fault pair from:
   - local signed-log relative changes;
   - per-metric robust ranks and shares;
   - local-versus-system contrast;
   - error/latency/load coupling features that distinguish packet loss from
     latency-only delay.
3. Select the schema and pair weight only on declared RE1-SS development data,
   then perform one final fit on RE1-SS repetitions 1-3 plus consumed RE1-OB
   repetitions 1-3. Candidate packets receive only the frozen artifact and scores,
   never labels, source paths, repetition IDs, or training case identities.
4. Preserve the NVIDIA evidence-analysis stage. Deterministic synthesis may
   choose the final service/fault only from candidate-visible scores and must
   preserve provider and synthesis raw-response replay.
5. Produce a P112 paired baseline artifact that binds the historical P111
   model, prompt hashes, system prompt hash, endpoint, API, decoding settings,
   implementation, packets, and raw responses. Missing fields fail closed.
6. Run the P111 baseline and P112 candidate on the same frozen OB repetition-4
   cases before revealing either score.

## Acceptance gates

### Development selection evidence

- RE1-SS repetition-4 service Top-1 `>= 0.80`;
- fault accuracy `>= 0.72`;
- loss accuracy `>= 0.60` and delay accuracy `>= 0.60`;
- zero truth leaks, invalid citations, harmful actions, executed actions,
  provider errors, duplicate outputs, missing outputs, and unknown outputs.

### Final blind acceptance

- RE1-OB repetition-4 service Top-1 `>= 0.84`;
- service Top-3 `>= 0.92`;
- overall fault accuracy `>= 0.84`;
- loss and delay accuracy each `>= 0.60`;
- evidence precision `>= 0.95`;
- no negative paired delta versus the frozen P111 baseline for Top-1 or fault
  accuracy, and at least one is strictly positive;
- two-run service/fault joint agreement `>= 0.90`;
- all safety counters exactly zero.

Release remains false without an out-of-band cryptographic reviewer identity,
even when all model-quality gates pass.

## Stop conditions

- Stop after the RE1-SS repetition-4 selection decision. Repetition 5 is
  recorded as contaminated and cannot satisfy any gate.
- Stop after freezing P112; no changes to hashed code or configuration before
  OB repetition 4 scoring.
- If final blind gates fail, report the failure and move to a new external
  dataset. Never tune on OB repetition 4.
- Never download or use the multi-gigabyte RE2 set merely to rescue a failed
  gate without a separate plan and resource review.
