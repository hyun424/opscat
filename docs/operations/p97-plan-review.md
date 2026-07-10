# P97 Plan Review

## Reviewed plan

1. Define tests before production code.
2. Build one loopback-only disposable workload server and reset it before every arm.
3. Separate scenario truth from the visible observation contract.
4. Execute no-action, human-runbook, and OpsCat arms with the same case and seed.
5. Derive outcomes from measured post-state and counterfactual deltas, never from an `expected_status` field.
6. Treat safety violations as release blockers.
7. Publish smoke and full-matrix evidence with explicit synthetic-lab limitations.

## Adversarial review

### Rejected: fixture post-check scoring

The existing offline evaluators can verify deterministic policy behavior but cannot show that an action caused recovery. P97 must mutate lab state and re-observe the workload.

### Rejected: unrestricted shell or Docker control

Arbitrary commands would make a benchmark more dangerous without making its causal evidence more trustworthy. P97 permits only enumerated in-process actions against an ephemeral loopback lab.

### Rejected: exposing the answer to the selector

`root_cause`, `required_actions`, harmful-action maps, runbook answers, and expected outcomes stay in the experiment coordinator. Selector input contains only observations an operator could plausibly see.

### Rejected: one aggregate score

A high mean cannot compensate for data loss, unsafe mutation, false recovery claims, or action outside the lab. Safety counters are hard gates and results are also reported per family, split, route, and intervention arm.

### Rejected: production-quality claim from a synthetic lab

The lab establishes evaluation infrastructure and comparative causal evidence. It does not validate production connectors, vendor APIs, real infrastructure permissions, or unattended production operation.

## Security boundary

- Bind only to `127.0.0.1` on an ephemeral port.
- Accept no request-controlled endpoint or command.
- Use a closed action registry.
- Reset state for every arm and seed.
- Record all attempted and blocked actions.
- Make external network, filesystem mutation, subprocess execution, credentials, and production mutation unavailable by construction.

## Acceptance review

- Exactly 120 deterministic cases across 12 operational families and 10 stress variants.
- Stable 60/20/20 development/validation/blind split.
- Identical initial fingerprint across all three arms for a case/seed.
- Real HTTP observation count greater than zero.
- Fixed action execution changes observable post-state.
- Natural-recovery and harmful-action controls prevent “always act” from scoring well.
- Missing/conflicting telemetry can produce `unverified` or escalation instead of false certainty.
- Zero hard safety violations.
