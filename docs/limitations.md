# Limitations

OpsCat uses production-grade packaging, testing, replay, and release-evidence practices, but its autonomous behavior is qualified only in deterministic local/mock/sandbox environments.

Not proven or enabled:

- production or staging mutation
- credentialed execution or auth completion
- live connector writes
- Kubernetes, cloud, database, or network changes
- arbitrary shell, subprocess, free-form, or LLM-generated command execution
- production incident reduction or operator replacement
- broad generalization beyond the published frozen datasets and fixtures

Public benchmark results must be read with their manifests, denominators, holdout rules, and source-quality limitations. A green release gate means the bounded claim passed, not that production autonomy is safe.
