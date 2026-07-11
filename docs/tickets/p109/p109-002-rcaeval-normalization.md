# P109-002 RCAEval Normalization

Discover RCAEval cases and deterministically normalize multimodal telemetry
while preserving raw hashes, timestamps, services, topology, traces, and logs.

Emit `p109.rcaeval_case.v1` with physically separate
`candidate_visible_evidence` and `scorer_only_truth` envelopes. Candidate
serialization must be incapable of resolving the truth handle.
