# P164 Plan Review

Decision: approved with a realistic-loopback-only claim.

- Represent gateway, checkout, database, and worker telemetry through
  Prometheus-, Loki-, trace-, deploy-, and health-shaped loopback endpoints.
- Cover six fault families and healthy/precursor/incident windows.
- Prove redaction and reject DNS, redirects, unknown paths, and non-loopback
  targets.
- Count loopback requests separately from external network calls.
- Do not call generated loopback data real staging or customer telemetry.
