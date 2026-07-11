# P114 evidence adjudication plan

## Objective

Replace P113's brittle single prototype decision with an evidence graph,
deterministic hypothesis lattice, and constrained LLM adjudicator. P114 may
improve diagnosis selection but never receives remediation authority.

## Scientific claim

All RE1 systems and cases are consumed. P114 does **not** claim fresh-system
generalization. It targets fresh-case and fresh-modality validation on RCAEval
RE2. RE2-SS is development data; a separately frozen RE2-OB run is the first
acceptance set. RE2-TT is reserved for a later same-artifact confirmation after
resource review.

Official sources:

- https://github.com/phamquiluan/RCAEval
- https://zenodo.org/records/14590730

## Architecture

1. Normalize metrics, logs, and optional traces into an immutable evidence graph.
2. Generate typed `{service, fault}` hypotheses using deterministic detectors.
3. Require sufficient joint candidate recall before any LLM evaluation.
4. Let NVIDIA select only a frozen hypothesis ID and evidence IDs.
5. Reject invented IDs, unsupported citations, action text, commands, secrets,
   writes, or mutations and fall back to the deterministic rank.
6. Freeze source, parser, features, model, prompt, decoding, code, gates, and
   blind case IDs before evaluator-owned labels are opened.

## Development sequence

- Quarantine RE1 and P113 case-level artifacts as consumed development inputs.
- Use leave-one-system-out RE1 evaluation to repair candidate generation.
- Add RE2-SS multimodal development and modality ablations.
- Gate the LLM on candidate recall: it cannot select a missing correct answer.
- Freeze once, then score RE2-OB once. Stop on failure; do not tune.

## Acceptance gates

Development candidate gates:

- service Top-5 candidate recall at least 0.85;
- joint service+fault candidate recall at least 0.70;
- evidence precision at least 0.95;
- every fault-family candidate recall at least 0.60.

Fresh RE2-OB gates:

- service Top-1 at least 0.60 and Top-3 at least 0.80;
- fault accuracy at least 0.60 and each fault at least 0.45;
- joint candidate recall at least 0.75;
- evidence precision at least 0.95 and abstention at most 0.20;
- LLM delta is nonnegative against deterministic fallback overall and per fault;
- raw contract at least 0.95 and repeat diagnosis agreement at least 0.90;
- replay and diagnosis preservation exactly 1.0;
- all truth-leak, action, credential, shell, write, adapter, and mutation counters zero.

These are minimum credibility gates, not an operator-replacement claim.

## Stop rules

- Do not run LLM adjudication if deterministic joint candidate recall fails.
- Do not score before a complete, timezone-aware freeze.
- After the first blind score, RE2-OB becomes consumed regardless of result.
- Do not weaken gates or tune from blind labels.
- Missing or unverifiable evidence always fails closed.

## Explicit non-goals

No auth, production connector, remediation execution, unrestricted shell,
credential use, hosted SaaS, or unattended-operation claim is added in P114.
