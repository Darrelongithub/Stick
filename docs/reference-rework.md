# Reference rework: baseline and direct observations

## Baseline

Restored tracked files from `8fbe44b`, the mainline parent of PR #9's merge
`014585e`. This removes the rejected generated rebuild and native FIFO host
patch. No installed ShimeLinux files have been changed by this repository work.
The user's pickup regression has not been reproduced in a desktop session;
restoring XML alone cannot undo a patched host binary, if one was installed.

## Actual reference

Tracked `output.mp4`: 1920×1080, 24 fps, about 237.875 seconds. Directly
inspected an overview across its duration and 24 timestamped frames at
30.000–35.750 seconds. This is not a claim to have reviewed every frame.

Observations visible in those samples:

- Orange has a hollow ring head. The other colored characters visible in the
  overview have filled heads. A uniform hollow-headed crew is not faithful.
- At 30–35.75s Orange makes exaggerated bent-knee, leaning and reaching poses;
  there are held anticipation poses as well as quick changes. This is not a
  neutral walking loop and should not be treated as one.
- Body scale in screen pixels varies with shot framing; do not derive a rig
  by comparing raw sizes across different shots.
- Contact and silhouette should be compared in a stable shot, preserving the
  sequence order and actual timestamps, before changing generated art.

Reproduce evidence (Pillow + PyAV required):

```sh
python tools/sample_reference.py --start 30 --step .25 --count 24
```

Outputs full-resolution timestamped PNGs and a sequence sheet under ignored
`preview/reference/`. This tool only samples video; it does not generate art.

## Interaction guardrails

`test_shimelinux_interaction_contract.py` checks all four restored packs:
Dragged references Pinched; Pinched uses the native Dragged class; Walk/Run
remain Move actions; floor travel sequences retain TargetX; Dragged, Thrown,
and Fall behaviors remain present. These are XML contract tests, not live
mouse or compositor tests. Baseline plus these guards: 58 unittest tests pass.

## Next visual milestone

Select a stable walking sequence from the video and compare one character at
matched body height. Keep the restored roaming/pickup behavior. Produce a
small preview before replacing any shipped animation frames. No new rig or
animation changes have been accepted or applied in this rework yet.

## First directly extracted motion prototype

`tools/extract_reference_motion.py` now extracts Orange's 31.000–35.000s
stepping/leaning action: 96 original source frames at 24 fps. It keys the orange
silhouette from this specific unobstructed shot, preserves the hollow head,
uses one crop/scale across the entire sequence, and retains source timestamps.
No procedural skeleton or invented in-between poses are involved. Original
RGB is replaced with the pack's Orange color; edge alpha is a hard color mask
before downsampling, so this is a review prototype, not finished production art.

```sh
python tools/extract_reference_motion.py
```

Review `preview/reference/orange-step/motion.gif`, `poses.png`, and `source.json`.
The GIF repeats for review, but the source action is **not a seamless loop**.
It has not been wired into the shipped XML, and it is not a replacement walk
cycle. Next work is selecting additional source actions, separating shot/camera
motion from mascot motion, and adapting approved sequences to host anchors and
tick timing without losing their source poses. Roaming/pickup remain unchanged.

## Integrated reference additions (supersedes the prototype-only milestone)

Eight finite actions / 207 transparent PNGs are now integrated for the four
existing pack figures. Manifest: `tools/video_actions.json` with source SHA-256,
source intervals and exact pose order. Generator: `tools/build_video_actions.py`.

- Orange: VideoLeanStep, VideoKneeLift
- Green: VideoRaiseArms, VideoReach
- Blue: VideoReach, VideoLean
- Yellow: VideoStep, VideoLean

Each action is `Animate`, `Loop=false`, one pass of unique frame filenames at
40ms per pose. Source 24fps masks are signed-distance resampled at 25fps rather
than alpha crossfaded (which would create double limbs). Source shot scale is
fixed, horizontal screen translation removed, and each shot's maximum body
height fitted into a 110px body envelope. This retains source proportions within
the clip, but matching older stock art across action boundaries remains a
visual concern; these are not new hand-authored entry/exit transitions.

Explicit NextBehaviorList Add=false returns to stock floor walking/running.
Thus these new actions do not immediately replay themselves. They may be
selected again after roaming; this is not a claim of never repeating any action
for the lifetime of the app. Existing walk cycles naturally remain cyclic.
No global idle queue or host binary patch is required.

`docs/video-actions-once.gif` plays the eight clips once, holding shorter clips
on their final pose for comparison; there is no GIF looping extension.
The GIF's final pose holds are comparison-only, not extra XML pose durations.

Verification: 60 unittest tests pass; validator passes; re-running patch_xml.py
is byte-identical. New tests verify source digest, finite actions, unique pose
references, duration mapping, safe image bounds, explicit roaming successors,
and preservation of Dragged/Pinched and target-driven Walk/Run.

**Limits:** no real ShimeLinux desktop run here, no proof pickup is repaired on
the user's installed binary, and no claim every action in the video is now
implemented. The full timeline was catalogued, but eight additions use selected
reviewed intervals. Red remains excluded from shipped assets because his draft
has obscured feet; the existing pack has four image sets. Raster interpolation
cannot recover hidden anatomy or create missing source poses. Further clean
source sequences and live host testing are still needed for the complete
whole-video request.
