# P109-006 Remediation Outcome Benchmark

Compute attempt success, first-attempt recovery, mean attempts, verified
recovery, duration, harmful actions, unnecessary actions, and per-family gates.

Reuse P97 measured-post-state semantics. Emit verified recovery, harmful,
unnecessary, no-effect, and unverified classifications; compare with a matched
no-action/natural-recovery control when supplied. Every metric has numerator,
denominator, nullable value, and unevaluable reason.
