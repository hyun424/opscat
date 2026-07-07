# Connector SDK Guide

This guide explains how to add a safe fixture-backed connector to OpsCat. P5 connector work is open-source/local-first: connectors should be useful for demos and evals without requiring real provider access.

Reference template: `examples/connectors/example_connector.py`.

## Core contract

A connector exposes:

- `connector_id`: stable unique ID such as `example.status`.
- `capabilities`: a mapping of capability name to `ConnectorCapability`.
- `call(request: ConnectorCallRequest) -> ConnectorCallResult`.

Every `ConnectorCapability` must define:

- `name`;
- `description`;
- `risk_level`;
- `read_only`;
- `required_role`;
- `requires_approval` for write-like actions;
- `required_secret_name` when a local secret is needed.

## Secret handling

Use a narrow `required_secret_name`; do not request a broad token. No broad token should be necessary for fixture mode. The `ConnectorService` resolves the secret and injects it into the connector payload as `auth_token`. Connectors must never return or audit the raw token.

## dry-run and write-like actions

Write-like connectors must be dry-run by default. No live mutation by default. If a connector previews Slack messages, GitHub issues, deploy rollbacks, or tickets, return a redacted preview and mark the result as not sent/created.

## Redaction

Use `redact_value` or `redact_text` before returning provider-shaped data. Tests should assert that tokens, emails, API keys, and fixture secrets do not appear in connector results, audit events, or incident reports.

## Idempotency

Connector callers should provide an idempotency key. The service records replay data and rejects conflicting re-use. Connector authors should keep calls deterministic so idempotency replay is useful.

## Provider failures

Failures must return `ConnectorCallResult(ok=False, ...)` or raise only within the provider boundary. The service turns provider exceptions into fail-closed results and can escalate when an incident context is present.

## Connector eval requirements

Every new connector should add connector eval coverage before being treated as release evidence. Cover at least:

1. fixture success;
2. missing credential fail-closed behavior;
3. provider failure or malformed response;
4. redaction of sensitive fields;
5. idempotency replay/conflict when relevant.

## Minimal template checklist

- No broad token.
- No live mutation by default.
- Fixture success path.
- Missing secret path.
- Provider failure path.
- Explicit `ConnectorCapability` metadata.
- Tests through `ConnectorRegistry` and `ConnectorService`.
