# P110 Plan Review

## Initial verdict: REJECT

Independent critic review rejected the first implicit plan because it lacked a
P110 contract, live-provider authority limits, anti-leak guarantees, budget
limits, statistical minimums, and a fail-closed release gate.

## Repairs incorporated

- Pinned the smallest official labeled suite, RE1-OB (31 MB compressed,
  125 cases), instead of downloading the 4.21 GB RE2 corpus.
- Separated candidate packets from scorer truth and prohibited normalized P109
  envelopes from entering prompts.
- Added mock, replay and explicit live modes with content-addressed caching.
- Added citation existence checks, candidate-score distrust and harmful-action
  blocking.
- Added minimum sample/cell requirements, bootstrap intervals and repeated-run
  agreement reporting.
- Limited online authority to pinned dataset acquisition and opt-in NVIDIA
  inference; all remediation remains advisory and non-executable.

## Revised verdict: APPROVED FOR IMPLEMENTATION

Implementation may proceed test-first. Release qualification remains impossible
until a real labeled holdout has been scored and independent verification binds
all resulting hashes.

## Implementation review: REJECTED, remediation in progress

The first adversarial code review reproduced forged-release paths despite the
green targeted suite. P110-010 therefore reopens implementation to seal scorer
truth and bind source, replay, batch, evaluation, implementation, and review
provenance. The measured 25-case result remains explicitly unqualified until
the repaired path passes an independent re-review.

## Local re-review verdict: PASS; hard release remains closed

After P110-010, a separate verifier reproduced source checksums and final merge
artifacts, ran 59 P110 tests plus Ruff/mypy, rejected eight forged paths, and
confirmed zero action authority. A subsequent adversarial review proved that a
self-attested JSON review and synthetic reports could still imitate live calls.
P110 therefore preserves and replays raw responses, while refusing to mark the
hard release qualified without out-of-band cryptographic reviewer identity.
