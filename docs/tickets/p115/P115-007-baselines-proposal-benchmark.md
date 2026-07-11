# P115-007: deterministic and constrained proposal baselines

Implement a byte-stable deterministic baseline that ranks action-pack IDs using
diagnosis, evidence completeness, prerequisites, contraindications,
reversibility, blast radius, validation, and rollback metadata. Implement a safe
null baseline that chooses no-action, investigate-more, or escalate whenever
evidence or authority boundaries are incomplete.

Only after those baselines pass may an optional constrained LLM benchmark select
from frozen action-pack IDs and first-class abstention labels. Unknown IDs,
invented actions, malformed JSON, commands, credentials, mutation language, and
missing evidence citations fail closed to deterministic fallback.
