# Recovery from the supplied ShimeLinux stall log

## Observed evidence

The user's log stops Green on `Bonk` at 10:57:13, then jumps to Orange's drag
interaction at 11:36:32. Orange subsequently selects actions and floor routes.
This does not prove global pause, movement on screen, or that every mascot
stopped for the same reason.

It does expose a configuration deadlock: Bonk references Hurt followed by
Stand without a reference Duration. Stand is Stay, which is indefinite while
its floor remains valid. Pose durations do not make Stay finite. Manual drag
can interrupt it, explaining why a mascot may resume after interaction.

## Corrections

- Bonk now finishes Hurt then finite Animate Idle, rather than indefinite Stand.
- Other unbounded Stand references receive a 12-tick reference Duration. Stand
  itself remains available for native host interactions; it is not deleted or
  globally converted into a different action type.
- Validator rejects unbounded Stay references in finite Sequence actions.
- Repeat checks reject both `Behavior(Wave)` and ShimeLinux's actual
  `Behavior[name=Wave]` format. The old check only rejected the former.
- The same guard covers stock HoldOntoWall and HoldOntoCeiling waits, which
  repeatedly appeared in the supplied log. Generated Dance already uses the
  generated guard. These checks prevent immediate reselection where the host
  evaluates against the completing behavior; not a permanent never-repeat list.

Inspected upstream ShimeLinux's UserBehavior.kt: its toString is
`Behavior[name=$name]`. BehaviorBuilder uses the schema key NextBehaviourList;
English schema maps that to NextBehaviorList, so the new video-action successor
blocks are not renamed based on the older pack's different XML spelling.

## Climbing correction

The raster-warp in-betweens are removed. Every climbing tick now uses one of the
approved, scaled/padded original source silhouettes, not a morphed body.
The cadence is twice as long (30 wall ticks, 32 ceiling ticks), with integer
velocity distributed across those ticks to preserve cycle displacement. Holds
and key poses remain original artwork. Down still reverses the sequence and
vertical direction. Eight unrelated video-derived actions are unchanged.

This favors clean silhouettes over claiming continuous limb interpolation. It
does not solve every transition between the original climbing artwork, old
stock walking art, and generated/video art. In particular, different Orange
head styles and relative body/head sizes across those families remain a visual
consistency issue; no blind body-proportion redraw is included in this fix.

`docs/source-climbing.gif` now includes cumulative XML movement, rather than
showing an actor at a fixed anchor. It is still an illustrative Pillow preview,
not a capture of a live desktop. Plays one pass, not an infinite GIF loop.

## Verification

69 unittest tests pass, including the Node-executed JavaScript repeat guard for
both host strings, finite Bonk recovery, a regression injection of the reported
unbounded Stand problem, source-key image checks, integer movement and unchanged
cycle displacement. Pack validation passes for all four sets. The importer and
XML patcher remain byte-identical on rerun.

No real ShimeLinux desktop session is available here. A successful restart and
runtime observation on the user's system are still required; do not call the
whole visual/behavior complaint resolved from configuration tests alone.

On update, completely quit and restart ShimeLinux: copying XML cannot replace
an already-built action that is stuck in memory.
