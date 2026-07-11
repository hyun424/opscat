# P115-003: evaluator-owned hidden outcome contract and leakage controls

Define `p115.outcome_contract.v1` as evaluator-owned hidden data binding the
measured P116 action, no-action, and wrong-action arms, attribution windows,
harm predicates, recovery predicates, rollback predicates, and natural-recovery
controls.

Build leakage checks across candidate envelopes, action-pack fields, IDs,
filenames, paths, descriptions, ordering, validation names, rollback names,
prompts, logs, reports, and release Markdown. Hidden outcomes must never appear
in candidate-visible artifacts.
