# P113 decoupled RCA and fresh-system blind plan

## Objective

Make root-cause diagnosis a deterministic, evidence-bound result that cannot be
erased or altered by optional LLM narrative formatting, improve the consumed
P112 disk/service failure modes, and evaluate once on untouched RCAEval
Train Ticket data.

## P112 evidence driving the design

- the P112 deterministic model reached 76% service Top-1, 92% Top-3, and 68%
  fault accuracy on consumed RE1-OB repetition 4;
- the live candidate fell to 12% because 22 of 25 outputs failed closed;
- 20 cases returned too many advisory actions, four returned too many ranked
  services, and several cited evidence outside the selected allowlist;
- disk classification reached only 20%;
- safety counters remained zero.

P113 treats RE1-OB repetition 4 as consumed failure-analysis data. It can never
again satisfy blind or release evidence.

### Taint boundary

P112 repetition-4 labels, per-case errors, service/fault identities, thresholds,
feature choices, prompt examples, fixtures, weights, and regression expectations
are tainted for P113 release development. They cannot influence release-counting
code or model selection. Only the aggregate failure facts already sealed in the
P112 final summary may motivate architecture: diagnosis/narrative coupling,
provider contract noncompliance, weak disk-family performance, and weak service
localization. A machine-readable taint ledger must bind every allowed consumed
artifact and reject case-level P112 blind material from training/selection.

## Architecture

### Diagnosis plane

The diagnosis plane is represented explicitly as `deterministic_judgment` and
emits:

- ranked services and faults;
- evidence references selected from frozen candidate-visible evidence;
- calibrated confidence and explicit diagnostic abstention;
- model, packet, source, feature-schema, and result hashes;
- no actions, commands, credentials, or mutation authority.

Its validity depends only on packet/model/evidence contracts. Provider output
cannot change or delete the diagnosis.

### Narrative plane

The optional LLM plane is represented explicitly as `llm_advisory`. It receives
the sealed diagnosis plus bounded evidence and may emit only:

- a concise explanation;
- contradictions or missing evidence;
- at most three read-only inspection suggestions.

Malformed, unsupported, oversized, or unsafe narrative fails closed to an
empty narrative and zero suggestions while preserving the diagnosis. Provider
raw output, normalized narrative, and validation errors remain replayable.

### Result envelope

The top-level result reports separate `diagnosis_status`, `narrative_status`,
and `action_contract_status`. `action_contract_status` is always `disabled`;
no field in either plane can enable execution. Evaluators score the diagnosis,
raw provider contract, deterministic normalization, narrative, and action
safety as distinct surfaces.

Normalization never erases raw provider noncompliance. Reports preserve both
`raw_contract_status` and `normalized_contract_status`; raw validity remains a
release gate. Normalization is predeclared, bounded, deterministic, and cannot
invent evidence, services, faults, suggestions, or successful execution.

## Data governance

### Development

- RCAEval RE1-SS and RE1-OB are consumed development systems.
- Only repetitions 1-3 may be used for model selection, error analysis,
  regression tests, and calibration, and every use must be declared in the
  artifact. Repetition 4 is tainted by P112 analysis; repetition 5 stays held
  out and is not used to tune P113.
- Only sealed aggregate P112 final-summary facts remain an immutable regression
  baseline; P112 repetition-4 case-level outputs never enter P113 code or tests.

### Fresh blind system

- Pin official RCAEval `RE1-TT.zip` from Zenodo record `14590730`.
- Expected upstream MD5: `48a26925ce47fd4bcfbedbae4f31475b`.
- Treat all 125 Train Ticket cases as one final system-level blind set.
- Acquisition may validate bytes and archive safety, but no TT truth is scored
  until model, packet, diagnosis/narrative contracts, code, gates, and P112
  deterministic baseline are frozen.
- After first scoring, TT becomes consumed and no P113 tuning is allowed.

## Evaluation

### Deterministic diagnosis benchmark

Run the frozen P112 deterministic model and P113 diagnosis plane on the same
125 TT packets without an LLM call. Score service Top-1/Top-3, fault accuracy,
per-fault floors, calibration, abstention, and evidence validity.

### Narrative contract benchmark

Before revealing TT truth, choose a deterministic hash-selected 25-case subset
from the frozen case IDs only. Run NVIDIA twice. Measure schema validity, evidence
validity, diagnosis preservation, bounded suggestions, provider errors,
replay, and safety. Narrative quality cannot change diagnosis metrics.

## Acceptance gates

- service Top-1 `>= 0.80` and nonnegative delta versus frozen P112;
- service Top-3 `>= 0.92`;
- fault accuracy `>= 0.84` and nonnegative delta versus frozen P112;
- CPU, memory, disk, delay, and loss accuracy each `>= 0.60`;
- evidence precision `>= 0.95`;
- diagnostic abstention `<= 0.10`;
- narrative valid rate `>= 0.95` on both runs;
- raw provider contract validity `>= 0.90` and normalized contract validity
  `>= 0.95`, reported independently;
- diagnosis preservation `= 1.00` even for invalid narrative;
- diagnosis repeat agreement `= 1.00`;
- provider/synthesis raw replay `= 1.00`;
- invalid provider raw responses replay against the frozen packet hash even
  when no candidate context is embedded in their fail-closed projection;
- zero truth leaks, unsafe suggestions, executed actions, provider writes,
  credentials, shell commands, production adapters, and mutations;
- cryptographic independent-review gate remains required for release.

## Stop conditions

- Freeze before any TT truth scoring.
- On blind failure, report and stop; never tune on TT.
- Narrative failure never weakens diagnosis or enables an action.
- No production remediation is introduced in P113.
