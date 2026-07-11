# P111 benchmark artifacts

This directory contains the frozen P111 RCAEval blind evidence. Development,
validation, smoke, and per-batch provider outputs are intentionally ignored as
reproducible local working data. The merged blind baseline/candidate reports,
freeze manifest, paired comparison, repeat agreement, and fail-closed release
decision are retained for reviewer replay.

Repetition roles are fixed as development `1`, validation `2`, blind `3`, and
untouched reserve `4`. Repetition `5` is historical/contaminated and must not be
used to select a P111 configuration.
