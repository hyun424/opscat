# Changelog

All notable OpsCat local/mock release evidence changes are tracked here.

## Unreleased

### P5 OSS productization

- Added open-source quickstart, example environment, contributor docs, and safe issue templates.
- Added connector catalog permission previews, connector SDK docs, local fixture examples, and API docs.
- Added metadata-only secret lifecycle APIs and fixture incident import normalization.
- Added workflow CLI stats/drain/dead-letter operations.
- Added approval console action previews without browser mutation forms because auth deferred remains the P5 boundary.
- Added Night Autopilot policy audit endpoint and morning report evidence.
- Added self-observability metrics and CI verification profiles.
- Added OSS security policy and safe disclosure docs.
- Added release packaging docs, deployment dry run, and versioned evidence instructions.

### P4 evidence

- Local/mock incident agent loop with deterministic evals.
- Policy-gated mock actions with approval, execution attempt records, verification, escalation, and reports.
- Connector failure/idempotency evals proving fail-closed behavior.
- Server-rendered operator dashboard and release evidence index.

## Stable vs experimental

Stable in local/mock mode: tests, evals, fixture ingestion, local-header demo identity, mock action policy gates, connector evals, docs, and verification profiles.

Experimental: production deployment, real connector credentials, OAuth, auth/session UI, external metrics export, hosted workflow infrastructure, and real customer production use.
