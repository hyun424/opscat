# P114-008: one-shot RE2-OB blind run

Run deterministic candidate gates first, then paired NVIDIA adjudication only
if allowed. The first score consumes the acceptance set and cannot be tuned.

Status: done. The authoritative deterministic path passed all predeclared
gates on 90 cases. A second invocation is rejected by the immutable consumed
receipt.
