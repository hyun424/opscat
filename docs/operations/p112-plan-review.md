# P112 plan review

## Initial verdict

Independent critic verdict: **rejected until blockers were resolved**.

The critic required a pinned source manifest, a system-generic loader,
service-name-independent features, complete paired baseline binding, exact
freeze tests, and explicit contamination handling.

## Resolutions

- Added `p112.source_manifest.v1` for official RE1-SS with byte size, MD5,
  SHA-256, case count, taxonomy, license note, and citation.
- Reacquired and validated the completed official archive. The critic's ZIP
  read failure occurred while the background download was incomplete; the
  completed archive opens with Python and `unzip`, has 125 cases, and matches
  both upstream MD5 and locally recorded SHA-256.
- Added an additive system-generic loader instead of modifying P110/P111 hashed
  implementation files.
- Defined service-name-independent robust shift/rate diagnostics, canonical
  fault families, cross-service ranks/shares/contrasts, and loss/delay coupling.
- Model artifacts may contain aggregate scaled vectors and fault labels but
  reject service names, case IDs, source paths, and root labels.
- Promoted complete request-envelope and raw/synthesis replay binding to a
  mandatory P112 baseline/freeze gate.

## Contamination amendment

During implementation research, RE1-SS repetition 5 was evaluated for three
finite pair-weight candidates rather than only the selected candidate. It is
therefore marked contaminated and excluded from confirmation/release claims.
No RE1-OB repetition-4 prediction or score was generated. The final blind set
remains intact.

## Transfer amendment

The SS-only selected model passed same-system validation but failed on already
consumed OB repetitions. No OB repetition-4 data was accessed. The selected
feature schema and pair weight are therefore locked from SS validation, while
the final artifact may fit those fixed features on SS repetitions 1-3 and
consumed OB repetitions 1-3. OB repetition 5 is excluded. This is final-model
fitting, not holdout selection; repetition 4 remains the only acceptance set.

## Current verdict

**Approved for implementation and RE1-SS selection only.** Final RE1-OB blind
execution remains blocked until tests, complete paired freeze binding, and an
independent pre-freeze review pass.
