# OpsCat P96 Final Summary — Real Prometheus Read-only Shadow Connector

P96 is implemented. OpsCat now has its first real observability read path: a Prometheus connector that can execute bounded instant and range queries against a trusted configured endpoint and convert the result into normalized, tenant/workspace-scoped incident evidence.

## Completed tickets

- P96-001 — Security contract: the connector uses a configured endpoint, exact host allowlist, GET-only transport, bounded timeout, 2 MiB response ceiling, 100-series ceiling, six-hour range ceiling, and 1,200-point range/sample ceilings.
- P96-002 — RED contract tests: fixture default, real instant reads, destination blocking, HTTPS enforcement, query budgets, provider error redaction, evidence persistence, and CLI behavior were defined before implementation.
- P96-003 — Prometheus connector: `prometheus.readonly` now exposes `health.check`, `query.instant`, and `query.range`.
- P96-004 — Evidence bridge: successful connector results carrying normalized evidence create a scoped `Evidence` record and `connector_evidence_collected` timeline entry.
- P96-005 — Operator probe: `scripts/probe_prometheus.py` runs fixture mode by default and requires explicit `--mode real` for network access.
- P96-006 — Product integration: connector catalog metadata and `.env.example` document the optional endpoint and allowlist configuration.
- P96-007 — Verification: targeted connector, registry, catalog, lint, and type checks are green; full repository verification is recorded below.
- P96-008 — Release evidence: P96 is recorded in the README, connector permissions, roadmap, and release evidence.

## Security and operational boundary

- Fixture mode is the default and makes zero network calls.
- Real mode is explicit opt-in.
- Base URLs cannot come from connector request payloads; request-controlled destinations fail closed.
- The configured hostname must be present in `OPSCAT_PROMETHEUS_ALLOWED_HOSTS`.
- Plain HTTP is permitted only for loopback development; non-loopback endpoints require HTTPS.
- Only Prometheus GET endpoints `/api/v1/query` and `/api/v1/query_range` are used.
- Query length, query duration, estimated points, response bytes, returned series, samples per series, and timeout are bounded.
- Provider errors are normalized and redacted before audit or evidence storage.
- No auth feature was added. There is no remediation, write endpoint, action execution, production mutation, or unattended-production claim.

## Commands

Offline fixture probe:

```bash
uv run --no-sync --extra dev python scripts/probe_prometheus.py
```

Explicit local real-mode probe after setting `OPSCAT_PROMETHEUS_BASE_URL` and `OPSCAT_PROMETHEUS_ALLOWED_HOSTS`:

```bash
uv run --no-sync --extra dev python scripts/probe_prometheus.py \
  --mode real \
  --capability query.instant \
  --query up \
  --output-json /tmp/opscat-prometheus-probe.json
```

Targeted verification:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q \
  tests/test_prometheus_connector.py \
  tests/test_connector_contract.py \
  tests/test_connector_catalog.py \
  tests/test_p96_release_evidence.py
```

## Verification result

- Prometheus connector tests: 9 passed.
- Connector/catalog regression group: 43 passed.
- Targeted Ruff: passed.
- Targeted mypy: passed.
- Full verification: passed across compile, Ruff, mypy over 555 source files, the complete pytest suite, all eval/demo smokes, Docker Compose config, generated-artifact scan, and whitespace checks.
- Coverage: `80.48% >= 60.00%`.
- Live-provider limitation: no external Prometheus endpoint was contacted; the real HTTP contract was exercised deterministically through injected transports while fixture mode remained network-free.

## P97 handoff

P97 should feed collected Prometheus evidence into the live investigation loop so the agent can select additional read-only queries, compare competing hypotheses, stop when evidence is sufficient, and invoke the existing LLM judgment adapter without granting the model action authority.
