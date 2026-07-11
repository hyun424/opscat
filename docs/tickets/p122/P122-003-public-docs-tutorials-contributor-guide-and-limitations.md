# P122-003: public docs, tutorials, contributor guide, and limitations

## Goal

Refresh public documentation and contributor onboarding so the project is
usable, reviewable, and honest about what is proven locally and what is not
proven in production.

## Contract

- Refresh README, install guide, quickstart, tutorials, architecture, public
  contracts, sample deployment, local demo, runbooks, troubleshooting, FAQ,
  release evidence, limitations, upgrade/migration, compatibility, contributor
  guide, release notes, and benchmark/model cards.
- Require every capability claim to link to frozen evidence, test evidence, or
  an explicit limitation.
- Include the required public limitation statement whenever docs discuss
  production-grade packaging or production.
- Contributor guide covers setup, tests, docs, security, contracts, release
  evidence, issue/PR process, review expectations, and claim language.
- Docs contain no hidden credentials, production targets, mutation-enabled
  defaults, unsupported autonomy claims, stale commands, or broken links.

## Acceptance

Docs are complete enough for a new developer to install, run the local demo,
inspect replay evidence, understand public contracts, contribute safely, and
evaluate release claims. Tutorials distinguish production-grade packaging and
local qualification from unproven production autonomy. Auth remains deferred,
production mutations are prohibited, and exact-zero nonlocal authority is
visible in public claim language.

## Stop Rules

Stop if documentation claims production-safe autonomy, auth completion,
credentialed execution, operator replacement, production incident reduction,
live connector authority, or production mutation; if claims lack evidence or
limitations; if examples require secrets by default; if commands are untested;
or if docs hide local-vs-production boundaries.
