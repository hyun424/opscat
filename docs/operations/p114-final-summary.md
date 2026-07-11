# P114 final summary

## Decision

P114 passed its predeclared one-shot RE2-OB deterministic diagnosis acceptance.
The result supports a bounded diagnostic recommendation claim. It does not
support production remediation authority or complete human-operator
replacement.

## Frozen lineage

- official source: RCAEval RE2-OB, 90 cases;
- source SHA-256:
  `0605a36cdcad8a6ae0107f2357c9c91ecee2c4ab5d72579bffea0372d9747513`;
- freeze hash:
  `sha256:23281d2f4797ac36b0b4b449f802af2c62257bd0ac17a2ff770502fe77500fd2`;
- independent replay hash:
  `sha256:43ccb18bde3a00a2368556dfa377497192df6f5ec3bccbf8706785850b10169b`;
- consumed receipt hash:
  `sha256:96bd2976e78f45bc9ac64e5dd879f2e266008d35eb38d8d7ef5ebbdfcb28e1c6`;
- evaluation hash:
  `sha256:560921b8b723b29f320a5120586e1dcc087716b8bcacc61679ef1bb6b8d24778`;
- gate hash:
  `sha256:5425f5be4ce84867d6e444a431d9b497965b88bdafe195bf2cb81cbed75c18b0`.

An earlier freeze was invalidated before scoring after an independent review
found blind-integrity and fail-open safety issues. The implementation was fixed,
fully reverified, and frozen again. No score was produced from the invalidated
freeze.

## Blind result

| Metric | Result | Gate |
| --- | ---: | ---: |
| Service Top-1 | 81.11% | >= 60% |
| Service Top-3 | 94.44% | >= 80% |
| Fault accuracy | 72.22% | >= 60% |
| Joint Top-1 | 57.78% | >= 50% |
| Joint candidate recall | 96.67% | >= 75% |
| Evidence precision | 100% | >= 95% |
| Replay consistency | 100% | 100% |
| Diagnosis preservation | 100% | 100% |

Per-fault accuracy was CPU 66.67%, delay 100%, disk 66.67%, loss 46.67%,
memory 53.33%, and socket 100%. Every class remained above the frozen 45%
floor; loss and memory are the first targets for future improvement.

## Safety and one-shot controls

All required safety counters were present and zero: truth leak, LLM calls,
credential access, shell execution, external writes, remediation adapter calls,
executed actions, artifact authority violations, and source mutation. The
authoritative path has a static no-LLM/no-network/no-shell/no-remediation scan
and a fail-closed runtime ledger. Freeze, replay, and score artifacts use
exclusive creation. A second score attempt failed with
`acceptance_already_consumed`.

## Verification

`bash scripts/verify.sh --profile p114-release` passed 228 tests plus scoped
Ruff and mypy checks before the final freeze. The blind score was generated only
after that verification.

## Remaining limits

1. RE2-SS and RE2-OB are different systems but remain within the RCAEval RE2
   benchmark family; broader dataset and live-shadow confirmation are still
   needed.
2. Fault classification is weaker for loss and memory.
3. The benchmark tests diagnosis, evidence binding, replay, and authority
   boundaries. It does not prove that proposed remediations improve real system
   outcomes.
4. Production action execution remains intentionally disabled.
