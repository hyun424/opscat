# OpsCat P4 Eval Evidence Report

This report is the reviewer-facing evidence pack for OpsCat P4. It is written for an Agentic AI Engineer portfolio review: the goal is to show that OpsCat is not a log-summary toy, but a bounded local/mock on-call agent with state, tools, policy, approvals, verification, escalation, and reproducible safety evidence.

## Operator replacement claim

OpsCat's current claim is deliberately scoped:

> In a local/mock environment, OpsCat can handle routine first-response operator work: receive an alert, persist incident state, gather safe context, propose evidence-backed remediation, enforce deterministic policy, require approval for risky writes, execute only local/mock actions, verify recovery, escalate exceptions, and write an audit-friendly report.

The claim is **not** that OpsCat can yet replace a production SRE across real infrastructure. The P4 evidence proves the agent loop and safety architecture. Production replacement requires P5 work: real connector deployment, production authentication, OAuth/secrets operations, customer-side data boundary, hosted workflow workers, UI hardening, and security review.

## Golden incident evals

Current status: **23/23 golden incident scenarios pass** through `scripts/run_evals.py`.

The golden corpus covers incident and safety cases including:

- bad deploy / rollback PR draft;
- external API timeout;
- worker queue backlog;
- duplicate and stale alert handling;
- low-confidence ambiguous incidents;
- missing runbook context;
- protected auth/security/data domains;
- failed verification;
- prompt-injection-like log content;
- secret-bearing alerts and redaction expectations.

What the eval checks:

- expected root-cause signal appears in the serialized incident/report evidence;
- recommended action appears in agent output;
- policy decision matches `ALLOW`, `REQUIRE_APPROVAL`, `DENY`, or `ESCALATE`;
- supporting evidence count is sufficient;
- required post-checks are present;
- route matches auto-allow, waiting approval, resolved after approval, or escalation;
- escalation and redaction requirements are enforced.

## Coverage taxonomy

The golden corpus is governed by [`docs/eval-taxonomy.json`](eval-taxonomy.json). The policy is **high-signal scenarios over artificial volume**: add scenarios when they close a category, route, safety-focus, connector, or production-readiness gap; do not inflate the count with duplicate alert variants.

The current taxonomy locks coverage across incident categories, policy routes, and safety-focus tags so future changes cannot silently narrow the operator-replacement evidence.

## Connector safety evals

Current status: **7/7 connector safety scenarios pass** through `scripts/run_connector_evals.py`.

The connector eval report proves that the connector boundary is not just a happy-path abstraction. It includes:

- fake read-only success with audit events;
- missing credential fail-closed behavior;
- provider timeout classification as `connector_timeout`;
- malformed provider result fail-closed behavior;
- read-only contract violation classification as `connector_contract_violation`;
- idempotency replay without duplicate escalation side effects;
- conflicting idempotency key rejection before provider re-execution.

Important safety boundary: the P4 connector evals are fake/local and require **no real Slack/GitHub/Sentry side effects**. They exist to prove capability typing, fail-closed behavior, auditability, redaction, and replay/conflict protection before real integrations are enabled.

## Dashboard browser-contract E2E

The operator dashboard has dependency-free browser-contract coverage in `tests/test_operator_dashboard_e2e.py`.

The current E2E contract validates:

- inbox-to-detail navigation via stable links;
- stable `data-testid` hooks for future browser automation;
- evidence, timeline, action, execution-attempt, and report sections;
- report link exposure;
- no mutation forms before explicit permission UX exists;
- HTML escaping for untrusted alert text.

This is intentionally not a polished production UI. It is the minimum credible operator surface for local demo and future browser/visual tests.

## Reproduce locally

Run golden incident evals:

```bash
python scripts/run_evals.py --output-json /tmp/opscat-evals.json --output-md /tmp/opscat-evals.md
```

Run connector safety evals:

```bash
python scripts/run_connector_evals.py --output-json /tmp/opscat-connector-evals.json --output-md /tmp/opscat-connector-evals.md
```

Run the full release gate:

```bash
bash scripts/verify.sh
```

The full gate runs compileall, Ruff, mypy, pytest, coverage gate, golden evals, connector evals, local demo smoke, Docker Compose config validation, generated artifact scan, and whitespace diff checks.

## Known limits

P4 remains local/mock:

- header-based local auth is not production authentication;
- no real Slack/GitHub/Sentry calls are made;
- no production rollback, Kubernetes, cloud, database, or shell mutation exists as a product tool;
- connector credentials are modeled locally, but production OAuth/secret rotation is not complete;
- dashboard UX is server-rendered and contract-tested, not a polished approval console;
- evals are deterministic and synthetic, not live incident traffic;
- human replacement is limited to the demonstrated first-response loop and exception escalation model.

These limits are product guardrails, not hidden gaps. They keep the portfolio claim honest while showing the architecture needed for a production agentic operations system.

## P6 agentic eval suite

Current P6 evidence adds a dedicated agentic eval runner:

```bash
python scripts/run_agentic_evals.py --output-json /tmp/opscat-agentic-evals.json --output-md /tmp/opscat-agentic-evals.md
```

The P6 suite covers at least 20 local/mock scenarios across deploy regression, traffic spike, connector outage, queue backlog, missing secret/config, noisy logs, duplicate alerts, malicious payloads, replay, cross-workspace merge probes, and dangerous action attempts. It reports explicit thresholds for correlation accuracy, top root-cause match, runbook selection, risk classification, unsafe action blocking, and recovery verification. Dangerous-action fixtures require a 100% unsafe action block rate.

The P6 eval suite is additive to the P4 golden incident and connector safety evals; it does not require credentials and writes generated JSON/Markdown artifacts to caller-provided temp paths by default.
