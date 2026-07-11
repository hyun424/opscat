# P114 test specification

## Governance

- reject undeclared RE1/P113 case-level inputs;
- distinguish consumed development, fresh development, and frozen acceptance roles;
- bind source bytes, case IDs, parser, feature schema, model, prompt, decoding,
  implementation, gates, and timestamps;
- reject JSON round-trip drift, post-freeze code drift, overlap, and early scoring.

## Acquisition and parsing

- verify official size, MD5, SHA-256, expected 90 cases, taxonomy, and archive paths;
- reject traversal, symlinks, duplicates, decompression bombs, malformed records,
  and label-bearing candidate fields; drop individual non-finite telemetry samples,
  record their count and missing-evidence marker, reject malformed non-empty timestamps,
  and drop blank/non-finite unanchored rows while recording a missing-timestamp marker;
- parse metrics and logs; traces are optional and missing-modality safe.

## Evidence graph and lattice

- stable evidence and hypothesis IDs;
- topology/locality, temporal, metric, log, and trace support edges;
- explicit support, contradiction, and missing-evidence refs;
- deterministic output under order permutations and replay;
- candidate recall, per-fault coverage, calibration, and modality ablations.

## LLM adjudicator

- only frozen hypothesis/evidence IDs are selectable;
- malformed JSON, unknown IDs, invented services/faults, prompt injection, action
  language, commands, secrets, writes, and mutation requests fail closed;
- provider failure preserves deterministic fallback;
- raw and normalized contract rates are separate;
- two independent runs produce replayable receipts and agreement metrics.

## Evaluation and release

- scorer truth is evaluator-owned and absent from candidate artifacts;
- paired deterministic/LLM metrics include exact numerators and denominators;
- no missing safety counter can pass by default;
- failed candidate gates stop LLM calls; failed blind gates stop release;
- release evidence is aggregate-only and requires independent cryptographic review.
