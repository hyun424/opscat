# P115-008: frozen split, P116 outcome import, release evidence, and review

Freeze schemas, action packs, scenario matrix, partition manifest, baselines,
evaluator, authority scan, and acceptance gates before hidden outcomes are
opened or P116 measured results are imported. Bind imported P116 outcome
records by hash and verify action/no-action/wrong-action arms, replay,
attribution, and denominators.

Create `p115.release_evidence.v1` with hashes for every release artifact and an
independent review by a reviewer distinct from the implementation author. Final
release scoring is blocked unless P116 measured paired outcomes exist and all
auth, credential, execution, mutation, production-adapter, and action-authority
counters are exactly zero.
