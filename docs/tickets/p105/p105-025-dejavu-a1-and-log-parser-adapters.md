# P105-025 - DejaVu A1 and Log Parser Adapters

## Goal

Implement reviewed-local source adapters for DejaVu A1 database evidence and
actual Apache, Hadoop, and Zookeeper parser-backed deploy candidates.

## Scope

- future `scripts/materialize_p105_dejavu_a1_reviewed_local.py`
- future parser materialization boundary for Apache, Hadoop, and Zookeeper
- source registry and eligibility manifest integration
- private label ledgers for A1 and parser-derived sources

## Tests First

- Observe RED from P105-024.
- Add adapter-specific tests only when they support the macro contract.
- Keep parser failures and unmapped parser successes as `unsupported_family`.

## Implementation Notes

- A1 uses `/private/tmp/opscat-dejavu-A1/A1/metrics.csv`,
  `/private/tmp/opscat-dejavu-A1/A1/faults.csv`, and
  `/private/tmp/opscat-dejavu-A1/A1/graph.yml`.
- A1 `faults.csv` is private label input; public features come from
  `metrics.csv` and `graph.yml` before labels join.
- Only reviewed `db connection limit` A1 faults may be eligible for
  `database`.
- Record supplied A1 license metadata as CC-BY-4.0 plus license URL, citation,
  reviewer, privacy, redaction, and redistribution fields.
- Apache, Hadoop, and Zookeeper rows require actual parser output and reviewed
  deploy/config-regression predicates before counting.
- Coverage uses actual timestamps only.

## Acceptance

- A1 reviewed-local manifest, private label ledger, source hashes, coverage
  intervals, and provenance hashes are emitted.
- Parser manifests include parser version, line offset, parsed timestamp,
  parse status, redacted payload, source hashes, and eligibility decisions.
- No adapter counts unsupported-family rows.
- No adapter fabricates coverage, labels, partitions, incident groups, source
  diversity, or floor credit.

## Acceptance Commands

```bash
uv run --no-sync --extra dev pytest -q \
  tests/test_p105_dejavu_a1_materializer.py \
  tests/test_p105_log_parser_materializers.py \
  tests/test_p105_source_registry_eligibility.py
```

```bash
uv run --no-sync --extra dev python scripts/materialize_p105_dejavu_a1_reviewed_local.py \
  --metrics-csv /private/tmp/opscat-dejavu-A1/A1/metrics.csv \
  --faults-csv /private/tmp/opscat-dejavu-A1/A1/faults.csv \
  --graph-yml /private/tmp/opscat-dejavu-A1/A1/graph.yml \
  --license-name CC-BY-4.0 \
  --output-dir /tmp/opscat-p105-reviewed-dejavu-a1 \
  --review-status reviewed-local \
  --expect-source-hashes
```

## Stop Condition

Stop if A1 labels leak into public rows, parser output becomes heuristic family
authority, coverage is padded, license/privacy review is missing, or any
unsupported-family row receives release-floor credit.
