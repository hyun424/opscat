# P115-000: P114 diagnosis-to-action boundary contract

Define `p115.diagnosis_action_boundary.v1` as the only allowed bridge from P114
diagnosis evidence into P115 action selection. The contract binds the P114
source lattice, selected hypothesis or abstention, visible evidence IDs,
missing-evidence markers, uncertainty, expected utility placeholder, validation
handle, rollback handle, freeze receipt, and replay receipt.

Reject hidden scorer truth, invented evidence IDs, provider-private reasoning,
action text from P114, commands, credentials, post-freeze blind-label artifacts,
and any mutation or execution authority. The boundary is candidate-visible and
offline only.
