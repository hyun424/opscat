# P115-005: counterfactual paired scoring

Define `p115.paired_score.v1` to compare the selected label against measured
P116 action, no-action, and wrong-action outcomes. Recompute recovery, harm,
collateral damage, recurrence, rollback success, unnecessary action, and
outcome-weighted utility from raw measured observations rather than submitted
success fields or textual expected outcomes.

Final P115 scoring must fail closed when P116 measured paired outcomes are
missing. In that state, P115 may report `p115_contract_ready` but not
`p115_outcome_qualified`.
