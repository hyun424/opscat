# P106-008 - Optional LLM Advisory

## Goal

Allow a strict mock-by-default advisory packet to nominate registered
capabilities without giving the model authority over safety or scoring.

## Contract

- Provider packets include public evidence, closed registry capability IDs, no
  scorer labels, no secrets, and zero-authority boundary flags.
- Advisory output may include capability IDs and rationale only.
- Forbidden fields include raw action type, policy override, confidence,
  forecast probability, expected value, risk score, and P107 unlock signals.
- Unregistered, duplicate, production-targeted, prompt-injected, shell, secret,
  or malformed proposals fail closed to deterministic fallback.

## Acceptance

LLM output cannot introduce actions, set expected value, override policy, change
probability, bypass gates, or unlock P107.
