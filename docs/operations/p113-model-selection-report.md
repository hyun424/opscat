# P113 deterministic model selection report

## Boundary

- Inputs: official RCAEval RE1-SS and RE1-OB repetitions 1-3 only (150 cases).
- Excluded: all RE1-OB repetitions 4-5 case-level material and every RE1-TT
  label/path/result.
- Method: deterministic leave-one-repetition-out cross-validation.

## Result

The existing service-agnostic scaled nearest-prototype model remains frozen for
P113. Its aggregate development CV reached service Top-1 `0.846667`, service
Top-3 `0.980000`, fault accuracy `0.766667`, and minimum per-fault fault
accuracy `0.633333`.

No tested variant improved the full objective:

| Variant | Top-1 | Top-3 | Fault | Fault floor | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| current | 0.846667 | 0.980000 | 0.766667 | 0.633333 | freeze |
| no coupling | 0.853333 | 0.966667 | 0.766667 | 0.666667 | reject: Top-3 regression |
| no share/rank | 0.766667 | 0.940000 | 0.793333 | 0.733333 | reject: service regression |
| raw evidence | 0.146667 | 0.346667 | 0.233333 | 0.100000 | reject |

Pair-weight variants were identical to the current model. The choice was made
before any TT truth scoring and does not use P112 repetition-4 case-level
feedback.
