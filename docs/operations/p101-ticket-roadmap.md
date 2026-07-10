# P101 Tool-Using Hypothesis Investigator

## Outcome

Turn the P100 stateful responder into an investigator that starts without incident
evidence markers, ranks competing diagnostic hypotheses from the symptom, chooses
read-only tools, incorporates returned evidence, and only then acts or escalates.

## Tickets

- **P101-001 — Runtime investigation contract and RED tests**
- **P101-002 — Closed read-only diagnostic tool catalog**
- **P101-003 — Hidden-evidence diagnostic lab boundary**
- **P101-004 — Symptom-derived competing hypotheses**
- **P101-005 — Information-seeking tool selection**
- **P101-006 — Negative-result anti-anchoring and tool fallback**
- **P101-007 — Evidence incorporation and hypothesis re-ranking**
- **P101-008 — Evidence-gated action delegation to P100**
- **P101-009 — Privileged, ambiguous, and low-observability stops**
- **P101-010 — Equal-state direct/fixed-tool/investigator comparison**
- **P101-011 — Tool accuracy, efficiency, recovery-retention, and safety metrics**
- **P101-012 — 520-case repeated evaluation, CLI, docs, and verification**

## Stop condition

P101 is complete when the investigator receives no initial evidence markers or
scorer truth, executes only closed read-only diagnostic tools, discovers the
relevant diagnostic surface in at least 95% of eligible full-matrix arms, retains
at least 95% of the direct-visible P100 recovery rate, materially outperforms a
fixed-tool ablation, and passes every hard safety gate. The benchmark remains a
synthetic loopback evaluation and does not authorize production diagnostics or
remediation.
