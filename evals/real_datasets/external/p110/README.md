# P110 external data

This directory intentionally does not redistribute RCAEval telemetry.

Place the verified official archive at:

```text
evals/real_datasets/external/p110/raw/RE1-OB.zip
```

The acquisition/preparation CLI validates the exact byte size, upstream MD5,
SHA-256, archive paths and case count before any model evaluation. The default
holdout is repetition `5`, yielding 25 balanced cases (five services × five
fault families). The source manifest is committed; raw telemetry and provider
response caches are ignored.

Upstream sources:

- https://github.com/phamquiluan/RCAEval
- https://zenodo.org/records/14590730
