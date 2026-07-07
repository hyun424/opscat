# OpsCat P15 Ticket Roadmap — NVIDIA LLM Provider Opt-in

## Requirements Summary

P15-mini adds a real-provider path for NVIDIA hosted OpenAI-compatible models while preserving mock-by-default verification. The selected primary model is `nvidia/nemotron-3-ultra-550b-a55b`. The provider is opt-in, key-gated, and still passes through P14 schema validation, citation checking, and safety gate.

Boundary remains unchanged:

- no auth/session work;
- no default external model/API calls and no network calls during normal verification;
- no committed API keys or credentials;
- no production mutation, Kubernetes/cloud/database execution, unrestricted shell, action execution, or unattended production-operation claim.

## P15 Tickets

### P15-001 — NVIDIA Provider Interface

**Outcome:** Implement nvidia provider interface.

**Acceptance criteria:**

- NVIDIA provider uses OpenAI-compatible API with base_url https://integrate.api.nvidia.com/v1.
- Default model is nvidia/nemotron-3-ultra-550b-a55b.
- Provider is opt-in and never used by normal verify profiles.

### P15-002 — API Key Handling

**Outcome:** Implement api key handling.

**Acceptance criteria:**

- Provider reads NVIDIA_API_KEY or explicit injected api_key.
- Missing key fails with a clear local error before network calls.
- No API key is committed, logged, or included in reports.

### P15-003 — Prompt Contract

**Outcome:** Implement prompt contract.

**Acceptance criteria:**

- Provider sends P13 context packet plus required P14 schema instructions.
- Prompt requires JSON-only output and evidence citations.
- Prompt explicitly forbids following instructions inside logs.

### P15-004 — Response Parsing

**Outcome:** Implement response parsing.

**Acceptance criteria:**

- Provider extracts JSON from non-stream or stream-like responses.
- Invalid JSON fails closed via P14 validation.
- Reasoning content is not required or persisted.

### P15-005 — CLI Provider Selection

**Outcome:** Implement cli provider selection.

**Acceptance criteria:**

- scripts/run_llm_judgment.py accepts --provider nvidia.
- CLI accepts --model override and env default.
- Mock remains the default provider.

### P15-006 — Offline Testability

**Outcome:** Implement offline testability.

**Acceptance criteria:**

- Unit tests use fake NVIDIA/OpenAI-compatible clients.
- Normal CI/full verify performs no external calls.
- Network opt-in is documented separately.

### P15-007 — Release Evidence

**Outcome:** Implement release evidence.

**Acceptance criteria:**

- Final summary maps P15-001 through P15-007 to code/tests/docs.
- Release evidence documents exact opt-in command.
- ROADMAP records P15 implemented boundary.
