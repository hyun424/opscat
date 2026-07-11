# P109-008 CLI and Release Profile

Add deterministic JSON/Markdown commands and a `p109-release` profile binding
source, normalization, metrics, authority, and independent-review evidence.

The profile binds source manifest, raw artifacts, normalized corpus, both
benchmark reports, contamination report, exact authority scan, profile output,
reviewed implementation revision, and independent review hashes. It fails on
zero/missing required cells, any nonzero safety numerator, self-review, or stale
hashes.
