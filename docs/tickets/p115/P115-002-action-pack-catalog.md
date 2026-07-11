# P115-002: signed action-pack catalog

Define `p115.action_pack.v1` as a signed declarative catalog. Each action pack
requires action ID, family, signer/key ID, prerequisites, contraindications,
reversibility class, blast-radius estimate, expected effect, expected evidence,
validation query, rollback plan, and executor-disabled metadata.

P115 action packs are benchmark metadata, not authority. Reject unsigned packs,
credentials, commands, production target selectors, executable validation,
missing rollback for reversible actions, hidden outcome hints, and duplicate
action IDs.
