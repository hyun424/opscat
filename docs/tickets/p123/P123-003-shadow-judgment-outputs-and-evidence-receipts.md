# P123-003: shadow judgment outputs and evidence receipts

## Goal

Define observational shadow outputs for future real-artifact replay runs.

## Contract

- Outputs include cited observations, uncertainty, missing evidence, gap
  reports, replay references, and no executed remediation.
- Evidence receipts link each output to artifact hashes and replay run IDs.
- Output language separates read-only shadow findings from live operational
  proof.

## Acceptance

Future shadow runs produce inspectable evidence receipts and do not imply
write authority or executed action.

## Stop Rules

Stop if outputs claim remediation execution, omit evidence citations, hide
uncertainty, or imply production autonomy.

