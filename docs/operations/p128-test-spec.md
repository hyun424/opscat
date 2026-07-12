# P128 Adversarial Test Specification

Implementation is pending. This planning spec requires no source/test edits,
runtime access, credentials, staging access, production access, or mutation.

## Required Rejections

- Credential prompts, live connector calls, staging/production targets,
  mutation controls, hidden remediation triggers, shell/subprocess actions,
  LLM command execution, L4+ authority, unredacted secrets, and
  operator-replacement claims.

## Required Checks

- Evidence links resolve to replay receipts, report manifests, or limitations.
- Counter panels show exact-zero credential, live-call, staging mutation,
  production mutation, and authority escape values.
- Fail-closed reasons are visible and tied to blocked actions.
- Redaction state is visible for real-artifact evidence.

## Named RED Cases

- `ux_hidden_mutation_control`
- `ux_credential_prompt`
- `ux_live_connector_call`
- `ux_untraced_claim`
- `ux_secret_visible`
- `ux_missing_fail_closed_reason`
- `ux_operator_replacement_claim`
- `ux_nonzero_authority_counter`

