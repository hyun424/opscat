# P109 external evidence

`rcaeval_simple_data.csv` is an unmodified public Baro/RCAEval metric sample
from release `0.0.4`. Its SHA-256 is recorded in `source-manifest.json`.

This file is real upstream telemetry, but it contains no authoritative incident
root-cause labels. It proves source parsing and hash/provenance handling only;
it must never be used to claim diagnosis accuracy or a release-qualified real
benchmark result.

No MicroRemed code or result is redistributed. The repository did not expose a
root license at the pinned revision, so OpsCat provides only an independently
authored compatibility contract. Release evidence requires an externally
executed result bundle and an independent verifier.
