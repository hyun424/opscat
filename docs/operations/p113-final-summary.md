# P113 final summary

## Decision

P113 is complete and **not release-qualified**. The diagnosis gate failed, so
the optional NVIDIA narrative phase was not executed.

## Frozen evidence

- official RE1-TT cases: 125
- source SHA-256: `2b33b7ab07198e0d69f229e697bfcef794a656e8db73a1d732142effde17c595`
- freeze hash: `sha256:a98e2a469f06fb2e625ebc4f45b7c08278f43ed7d1d07572e382d827f9a7355d`
- model hash: `sha256:986b5f4ef4d36ed8bae54d4f3d18b1c84035447c8a4d7937ebfb4bb92f1a333f`
- diagnosis evaluation hash: `sha256:33e21b238c221b5c334df70609dc310fa50b3edcf392800bae39adc08944c8e0`

## Blind metrics

| Metric | Result | Gate |
| --- | ---: | ---: |
| service Top-1 | 31.2% | 80% |
| service Top-3 | 49.6% | 92% |
| fault accuracy | 32.0% | 84% |
| evidence precision | 100% | 95% |
| abstention | 0% | at most 10% |

Fault accuracy was CPU 56%, memory 8%, disk 28%, delay 20%, and loss 48%; all
five per-family gates failed. Diagnosis preservation, replay consistency, and
action-authority-disabled rates were each 100%. All evaluator safety counters
were zero.

## Interpretation

The deterministic model generalized poorly from RE1-SS/RE1-OB to RE1-TT.
LLM prose cannot repair that localization/classification failure because P113
intentionally prevents narrative output from changing the sealed diagnosis.
The correct next phase is a new model-development cycle over consumed systems,
followed by a genuinely unseen benchmark; it is not prompt tuning on TT.

## Boundary

No remediation was executed, no production adapter or credentials were exposed,
and no NVIDIA calls were made after the failed diagnosis gate. Auth remains
deferred. P113 evidence is a negative benchmark and must not be presented as a
production-autonomy claim.
