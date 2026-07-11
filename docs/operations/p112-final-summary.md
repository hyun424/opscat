# P112 final summary

## Decision

P112 is **not release qualified**. The phase is closed without tuning on the
revealed RE1-OB repetition-4 labels. Action execution remains disabled.

## Frozen evidence

- official blind source: RCAEval RE1-OB repetition 4, 25 cases;
- development source: RCAEval RE1-SS plus consumed RE1-OB repetitions 1-3;
- final freeze: `sha256:6cea15d94dba744c6499159d02c3097ab1949c25d864d1c6893f349fda907633`;
- model artifact: `sha256:986b5f4ef4d36ed8bae54d4f3d18b1c84035447c8a4d7937ebfb4bb92f1a333f`;
- baseline and two independent candidate runs used the same frozen packets,
  request envelopes, NVIDIA model, endpoint, API, prompt hashes, decoding
  settings, and implementation hash;
- the first freeze was superseded after the batch merger incorrectly rejected
  legitimate fail-closed predictions whose contract intentionally omits
  `candidate_context`; its artifacts remain under the superseded evidence path.

## Blind result

| Metric | P111 baseline | P112 candidate run 1 | Delta |
|---|---:|---:|---:|
| service Top-1 | 88% | 12% | -76 pp |
| service Top-3 | 100% | 12% | -88 pp |
| fault accuracy | 100% | 12% | -88 pp |
| evidence precision | 100% | 100% | 0 pp |
| abstention | 0% | 88% | +88 pp |

Candidate run 2 reached 24% service Top-1 and 24% fault accuracy. The two
candidate runs had 4% joint service/fault agreement, below the 90% gate. All
truth-leak, invalid-citation, harmful-action, executed-action, missing-output,
duplicate-output, unknown-output, and provider-error safety counters remained
zero.

## Root-cause separation

The deterministic cross-system model, scored independently of the LLM output
contract, reached:

- service Top-1 76%;
- service Top-3 92%;
- fault accuracy 68%;
- per-fault accuracy: CPU 60%, memory 100%, disk 20%, delay 100%, loss 60%.

It therefore missed the predeclared Top-1, fault, and disk robustness targets
even before provider formatting failures.

The live candidate then failed closed on 22 of 25 cases. The dominant contract
error was `too_many_advisory_actions` (20 cases), followed by four
`too_many_ranked_services` violations and unsupported evidence references.
This exposed an architectural mistake: deterministic localization was allowed
to run only after a fully valid LLM response, so optional narrative formatting
could erase otherwise replayable model judgments.

## Verification

- two independent pre-freeze reviews returned PASS/ACCEPT;
- `bash scripts/verify.sh --profile p112-release` passed 102 tests plus ruff and
  mypy before the final freeze;
- the complete pytest suite passed except five pre-existing P105 RabbitMQ tests
  that require a running Docker daemon; all loopback tests passed outside the
  sandbox;
- final release evidence failed closed on quality, repeatability, replay, delta,
  per-fault, and cryptographic-review gates;
- no production connector, mutation, command execution, or remediation action
  was enabled.

## Next phase constraints

P113 must not tune against RE1-OB repetition 4 as blind evidence. It may use the
now-consumed split only for failure analysis. P113 should:

1. make deterministic localization independent of optional LLM narrative
   validity while retaining fail-closed action output;
2. normalize bounded LLM output before validation or request an intentionally
   smaller contract;
3. improve disk and service localization on development-only data;
4. add contract-fuzz and provider-variance tests;
5. select and freeze a new untouched external-system split before making any
   release claim.
