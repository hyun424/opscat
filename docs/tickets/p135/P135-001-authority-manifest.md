# P135-001 - Authority bridge and strict manifest

## Deliverable

Implement exact P135 manifest/spec schemas and validation that binds every
artifact to an allowed P134 OA1 `LOCAL_READ_FILE` decision receipt.

## Acceptance

- Closed provider/format/signal set and bounded limits.
- Exact hashes, strict times, lexical unique IDs, safe relative paths.
- P134 contract/receipt/proposal/capability/estimate binding is revalidated.
- Every proposal requests only `OA1_LOCAL_ARTIFACT`; provider-shaped attachment
  is never represented as a P134 OA2 promotion.
- Invalid authority fails before filesystem access.
