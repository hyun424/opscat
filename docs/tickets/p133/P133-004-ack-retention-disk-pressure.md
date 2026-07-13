# P133-004 Acknowledgement, Retention, and Disk Pressure

Status: complete; independently reviewed and release-qualified.

Add local hash-bound acknowledgement and budgeted retention. Only exact owned
acknowledged events may be pruned after immediate identity/content
revalidation. Unacknowledged, foreign, unreadable, tampered, hard-linked, or
symlinked files block cleanup. Low space and unrecoverable pressure preserve the
cursor and active incident.
Cleanup unlinks/fsyncs the event before unlinking/fsyncing its ack; a crash may
leave only a valid orphan ack, which a later cleanup validates and removes.
