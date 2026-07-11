# P117 final summary

P117 is outcome-qualified for the frozen offline evidence-bound selection
benchmark. The current release evidence hash is
`sha256:d78464fc832618e0178923122c65f8a51a60a846da066389780084562026f3f4`.

- 600 episodes across 15 scenario families.
- Every episode contains an actual P114 hypothesis-lattice object and sealed
  lattice/replay hashes.
- Every eligible action binds a P115 offline-signed action-pack reference.
- Every utility decision binds the corresponding P116 paired record hash.
- Deterministic selection accuracy: 600/600.
- Contract and evidence-citation validity: 600/600.
- Harmful and unnecessary action selections: 0/600.
- Abstention precision and recall: 120/120.
- Expected calibration error: 0.02.
- Measured utility: 0.312135 versus safe-null 0.14.
- Replay agreement: exact.
- All auth, credential, executor, shell, subprocess, Kubernetes, cloud,
  database, network, online-policy, and production-mutation counters: zero.

The NVIDIA integration in P117 is deliberately parser-only and proposal-only;
it is not included in the qualified score. Malformed, invented, credentialed,
command-bearing, or mutation-bearing model output falls back to the
deterministic selector. A future model tournament may be reported only after
frozen repeated calls meet the P117 NVIDIA gates.

The 1.0 deterministic score is expected on this synthetic policy benchmark:
candidate-visible safety, missing-evidence, natural-recovery, and
human-authorization markers are intentionally explicit. This proves contract
composition, evidence binding, causal utility accounting, abstention, and
replay—not cross-system or production generalization. P120 owns that claim.
