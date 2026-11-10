# Animation audit

Generated from the shipped XML/PNGs by `tools/review_animations.py`.
GIF previews are written to ignored `preview/review/`; contact sheets are
`docs/animation-review-*.png`. This audit aligns anchors and plays pose
durations; it is not a substitute for the native host playback harness.

Pose-bearing named actions reviewed: **62**.

| Action | Sample character | Type | Poses | Verdict | Note |
|---|---|---:|---:|---|---|
| Backflip | Blue | Animate | 6 | KEEP | generated reference rig; margins/continuity checked |
| BrewPotion | Blue | Animate | 4 | KEEP | generated reference rig; margins/continuity checked |
| Cartwheel | Orange | Animate | 48 | KEEP | generated reference rig; margins/continuity checked |
| Cheer | Blue | Animate | 6 | KEEP | generated reference rig; margins/continuity checked |
| ClimbCeiling | Blue | Move | 48 | KEEP | generated reference rig; margins/continuity checked |
| ClimbWall | Blue | Move | 96 | KEEP | generated reference rig; margins/continuity checked |
| Coffee | Blue | Animate | 6 | KEEP | generated reference rig; margins/continuity checked |
| Crawl | Blue | Animate | 48 | KEEP | generated reference rig; margins/continuity checked |
| Cry | Blue | Animate | 6 | KEEP | generated reference rig; margins/continuity checked |
| CursorSlash | Blue | Animate | 3 | KEEP | generated reference rig; margins/continuity checked |
| Dance | Blue | Animate | 8 | KEEP | generated reference rig; margins/continuity checked |
| Dash | Blue | Move | 11 | KEEP | legacy stock/menu compatibility; excluded from autonomous reference pool |
| Dizzy | Blue | Animate | 5 | KEEP | generated reference rig; margins/continuity checked |
| DrawAlive | Orange | Animate | 6 | KEEP | generated reference rig; margins/continuity checked |
| Falling | Blue | Embedded | 48 | KEEP | generated reference rig; margins/continuity checked |
| FightCombo | Blue | Animate | 6 | KEEP | generated reference rig; margins/continuity checked |
| GlitchOut | Blue | Animate | 3 | KEEP | generated reference rig; margins/continuity checked |
| GrabCeiling | Blue | Stay | 16 | KEEP | generated reference rig; margins/continuity checked |
| GrabWall | Blue | Stay | 16 | KEEP | generated reference rig; margins/continuity checked |
| HuggedSolidAction | Blue | Embedded | 8 | REPAIR | legacy stock art touches canvas edge: hugged_solid01.png, hugged_solid02.png, hugged_solid03.png |
| HuggingSolidAction | Blue | Embedded | 8 | REPAIR | legacy stock art touches canvas edge: hugging_solid01.png, hugging_solid02.png, hugging_solid03.png |
| Hurt | Blue | Animate | 3 | KEEP | generated reference rig; margins/continuity checked |
| Idle | Blue | Animate | 8 | KEEP | generated reference rig; margins/continuity checked |
| Inspect | Yellow | Animate | 8 | KEEP | generated reference rig; margins/continuity checked |
| Juggle | Blue | Animate | 7 | KEEP | generated reference rig; margins/continuity checked |
| Jump | Blue | Animate | 8 | KEEP | generated reference rig; margins/continuity checked |
| JumpRope | Green | Animate | 24 | KEEP | generated reference rig; margins/continuity checked |
| Meditate | Blue | Animate | 6 | KEEP | generated reference rig; margins/continuity checked |
| Mine | Blue | Animate | 4 | KEEP | generated reference rig; margins/continuity checked |
| PaperPlane | Blue | Animate | 4 | KEEP | generated reference rig; margins/continuity checked |
| Phone | Blue | Animate | 6 | KEEP | generated reference rig; margins/continuity checked |
| Pinched | Blue | Embedded | 7 | REPAIR | legacy stock art touches canvas edge: pinch01.png, pinch02.png, pinch03.png |
| PlayGuitar | Green | Animate | 4 | KEEP | generated reference rig; margins/continuity checked |
| PowerSlide | Blue | Animate | 4 | KEEP | generated reference rig; margins/continuity checked |
| PushUps | Blue | Animate | 4 | KEEP | generated reference rig; margins/continuity checked |
| ReadBook | Blue | Animate | 8 | KEEP | generated reference rig; margins/continuity checked |
| Resisting | Blue | Embedded | 1 | REPAIR | legacy stock art touches canvas edge: pinch04.png |
| Run | Blue | Move | 11 | KEEP | generated reference rig; margins/continuity checked |
| RunAffordance | Blue | Embedded | 11 | KEEP | legacy stock/menu compatibility; excluded from autonomous reference pool |
| Sit | Blue | Stay | 1 | REPAIR | legacy stock art touches canvas edge: sit01.png |
| SitAndDangleLegs | Blue | Stay | 6 | KEEP | legacy stock/menu compatibility; excluded from autonomous reference pool |
| SitAndLookAtMouse | Blue | Stay | 2 | REPAIR | legacy stock art touches canvas edge: sit01.png, sit_up01.png |
| SitAndLookUp | Blue | Stay | 1 | REPAIR | legacy stock art touches canvas edge: sit_up01.png |
| SitWithLegsDown | Blue | Stay | 1 | KEEP | legacy stock/menu compatibility; excluded from autonomous reference pool |
| SitWithLegsUp | Blue | Stay | 1 | KEEP | legacy stock/menu compatibility; excluded from autonomous reference pool |
| Sleep | Blue | Animate | 6 | KEEP | generated reference rig; margins/continuity checked |
| SnackTime | Blue | Animate | 4 | KEEP | generated reference rig; margins/continuity checked |
| Sneeze | Blue | Animate | 3 | KEEP | generated reference rig; margins/continuity checked |
| SpinKick | Blue | Animate | 6 | KEEP | generated reference rig; margins/continuity checked |
| Sprawl | Blue | Stay | 3 | KEEP | generated reference rig; margins/continuity checked |
| Stand | Blue | Stay | 8 | KEEP | legacy stock/menu compatibility; excluded from autonomous reference pool |
| StandAffordance | Blue | Embedded | 8 | KEEP | legacy stock/menu compatibility; excluded from autonomous reference pool |
| StandFromFloor | Blue | Animate | 4 | REPAIR | legacy stock art touches canvas edge: bounce01.png, bounce02.png, bounce03.png |
| Stretch | Blue | Animate | 6 | KEEP | generated reference rig; margins/continuity checked |
| SwordPractice | Blue | Animate | 5 | KEEP | generated reference rig; margins/continuity checked |
| Taunt | Blue | Animate | 6 | KEEP | generated reference rig; margins/continuity checked |
| Tinker | Yellow | Animate | 4 | KEEP | generated reference rig; margins/continuity checked |
| Tripping | Blue | Animate | 6 | KEEP | generated reference rig; margins/continuity checked |
| Victory | Blue | Animate | 7 | KEEP | generated reference rig; margins/continuity checked |
| WaitIdle | Blue | Animate | 1 | KEEP | single zero-velocity pose for native waiting idle |
| Walk | Blue | Move | 6 | KEEP | generated reference rig; margins/continuity checked |
| Wave | Blue | Animate | 4 | KEEP | generated reference rig; margins/continuity checked |

## Policy

- Generated reference actions are the autonomous repertoire and use hollow heads.
- Legacy stock actions remain for required host interactions/menu compatibility;
  they are not selected autonomously except required Fall/Dragged/Thrown/ChaseMouse paths.
- `REPAIR` flags edge-tight legacy art that should be redrawn before broader reuse.
