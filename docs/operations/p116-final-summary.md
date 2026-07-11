# P116 final summary

P116 is outcome-qualified for the standalone controlled local fault-action lab.
The current release evidence hash is
`sha256:9ce24fad9d1eba34da373efb058e9f13cfa7213cbc104e86f2a25ad4b4b2b3fb`.

- 120 paired records and 600 arm experiments.
- Arms: selected action, no action, wrong action, rollback action, and natural
  recovery.
- Helpful selected actions: 64/64 eligible records.
- Median recovery measurement-point reduction: 0.666667.
- Reset, initial comparability, rollback, and replay consistency: 1.0.
- Natural-recovery miscredit and wrong-action credit: zero.
- 127.0.0.1 synthetic lab only; no external network or production adapter.
- Production, credential, filesystem, subprocess, arbitrary-action, and
  unattended-operation authority counters: exactly zero.

The `p116-release` profile validates the persisted artifact self-hash and every
recorded source hash against the current repository. The recovery metric is a
deterministic measurement-point reduction, not wall-clock production MTTR.
These results qualify the controlled lab contract and causal accounting, not
real-world remediation effectiveness.
