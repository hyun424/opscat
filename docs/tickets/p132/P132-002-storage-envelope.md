# P132-002 Storage Envelope

Status: complete.

Add health-report count and directory-byte retention plus a configured minimum
free-space floor. Retention may delete only owned regular report artifacts
inside the allowlisted report directory. Low-space and `ENOSPC` failures must
fail closed. Failures before replace preserve the prior checkpoint; a
directory-sync failure after replace may leave only a newer hash-valid
checkpoint and must disclose durability uncertainty, reload it, and complete a
subsequent durable rewrite before qualification.
