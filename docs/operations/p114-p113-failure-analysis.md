# P114 consumed P113 failure analysis

P113 RE1-TT is consumed development evidence. This report is not blind or
release evidence and must not be used to describe RE2 as a fresh system.

## Aggregate diagnosis failure

- service Top-1: 39/125 (31.2%)
- service present anywhere in the five candidates: 81/125 (64.8%)
- service absent from all five candidates: 44/125 (35.2%)
- correct joint service/fault Top-1: 22/125 (17.6%)
- fault accuracy: 40/125 (32.0%)

The missing-candidate rate proves that an LLM reranker alone cannot solve the
problem: more than one third of true services were not selectable.

## Fault confusion

| True fault | Correct | Dominant wrong predictions |
| --- | ---: | --- |
| CPU | 14/25 | loss 7, delay 2, disk 2 |
| memory | 2/25 | loss 9, CPU 8, delay 6 |
| disk | 7/25 | loss 10, CPU 8 |
| delay | 5/25 | loss 12, CPU 8 |
| loss | 12/25 | delay 7, CPU 6 |

The prototype model over-selected CPU/loss and nearly erased memory. P114 must
therefore improve candidate generation and typed detectors before enabling LLM
adjudication. It must also report candidate recall separately from final Top-1.

## Governed conclusion

P114-003 and P114-004 remain blocked until the evidence graph can preserve
service-local and modality-specific signals across systems. P114-005 remains
blocked until joint candidate recall reaches its predeclared development gate.
