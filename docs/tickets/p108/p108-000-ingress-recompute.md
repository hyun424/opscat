# P108-000 - Raw P107 Ingress Recompute

Build a typed raw handoff pack and independently recompute P107 readiness.
Reject copied readiness booleans, missing raw evidence, forged hashes, fake
staging/live metadata, stale review, and any nonzero or extra authority counter.

Done when adversarial ingress tests prove every invalid pack fails before ledger
creation and valid immutable P107 evidence produces one content-bound identity.
