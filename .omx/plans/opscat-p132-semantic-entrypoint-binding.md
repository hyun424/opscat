# P132 semantic console-entrypoint binding repair

## Problem

P132 records the whole `pyproject.toml` file in supervisor source hashes even
though its safety claim depends only on the `opscat-monitor` console-script
mapping. Adding an unrelated later milestone command therefore makes promoted
P132 evidence stale and breaks every dependent verification profile.

## Behavior lock

1. Preserve exact source hashing for P132 runtime code and supervisor manifests.
2. Preserve fail-closed rejection when `project.scripts.opscat-monitor` is
   missing, malformed, or differs from `app.monitor_cli:main`.
3. Permit unrelated `pyproject.toml` edits that do not change that mapping.
4. Regenerate and validate promoted P132 evidence after the repair.

## Implementation

- Stop treating `pyproject.toml` as an indivisible supervisor source file.
- Recompute the current `opscat-monitor` mapping during release validation and
  compare it with the semantically bound value in supervisor evidence.
- Add regression coverage for both unrelated-script acceptance and monitor
  mapping drift rejection.

## Verification

- Targeted P132 runtime and release tests.
- Regenerated promoted P132 release evidence.
- P133 and P141 release profiles, proving the dependency chain is current.
