# P115-004: no-action, investigate-more, and escalate as first-class labels

Model `no_action`, `investigate_more`, and `escalate` as correct candidate
decisions rather than benchmark failures. Require investigate-more when
mandatory evidence is absent, no-action when intervention is unnecessary or
expected harm dominates, and escalation for permanently human-authorized
operations such as destructive data changes, credential/security changes,
irreversible migrations, and broad traffic shifts.

Scoring must penalize unnecessary intervention even when the service later
recovers.
