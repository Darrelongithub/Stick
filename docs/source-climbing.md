# Original Windows stickfigure climbing, with in-betweens

Source: https://github.com/Skittlq/alan-beckers-stickfigures-unofficial

Pinned revision: `6e32aeb3956912c1d7d8396d885cb2b61be63193`.
Selected original PNGs and pose metadata are under
`third_party/alan-stickfigures/`, with the upstream MIT license. The license is
also copied into each installed character directory.

## Approved poses preserved

The original five wall poses and eight ceiling poses replace the rejected
procedural IK rigs. Source key images are scaled/padded, not redrawn or
recolored, and remain pixel-exact at their original tick boundaries. Original
pose timing is preserved without personality timing accents or phase rotation.

A uniform per-character scale (never upscaled) fits its source canvases into a
128px interior; 16px padding produces 160px images. Anchors receive the same
transform. Integer velocity magnitudes are scaled/rounded. Blue, Yellow and
Green retain 1x; Orange uses 0.8421052631578947 to accommodate taller source art.

## Smoothing

Each held source pose is expanded to per-tick artwork: 15 wall frames and 16
ceiling frames at 40ms each. Motion estimation warps the nearest source
silhouette toward its neighbour, without RGB ghost-image blending. Source key
poses and total cycle duration/displacement are unchanged. Ceiling anchor
changes are interpolated and rounded to integers too. The final-to-first
transition is treated as part of cyclic climbing, not a new video action.

The nearest-source warp avoids an earlier rejected contour-intersection method
that visibly thinned limbs. A coverage guard rejects severe shrink/inflation.
This is raster-based in-betweening, not motion capture: some pose changes can
still be abrupt where correspondence between different drawings is ambiguous.
It cannot recreate source pixels clipped at a canvas edge.

Upstream's downward wall sequence repeats upward velocities. Our down sequence
reverses the pose list and negates vertical velocity. Wall hold retains the
first source wall pose; ceiling hold retains swing03. Green's oversized hang01
and the old procedural hold loops are not imported.

`docs/source-climbing.gif` shows one pass, aligned against drawn surfaces. Its
actor anchor is fixed to show silhouettes; it is not a velocity simulation or
a real desktop capture. There is no infinite GIF loop extension. Climbing can
cycle while travelling; the eight video-derived actions stay single-pass and
return to roaming.

## Reproduction

```sh
python -m pip install -r tools/requirements-reference.txt
python tools/import_classic_climbing.py
python tools/smooth_video_actions.py
python tools/patch_xml.py
python tools/make_motion_previews.py
python tools/validate.py
python -m unittest discover -s tests -q
```

`stickgen.py` skips source-authored actions; it cannot overwrite imported
climbing with procedural artwork. Vendored keyframes support exact pixel tests.
All literal pose vectors are validated as integers, catching the reported
ShimeLinux -0.42 config-load failure before installation.

## Video-action cleanup

The eight existing video-derived actions use motion-aligned neighbouring masks
to reduce contour chatter, with limited contour displacement and a coverage
guard to avoid erasing thin hands/feet. First/last frames are unchanged, as are
all 207 pose references, source intervals, durations, anchors and explicit
roaming successors. No wraparound blend or repetition is added.

An immutable compressed baseline of the already-keyed video frames, with source
video digest and baseline commit, is stored under
`third_party/video-motion-baseline/`. Smoothing reads this baseline rather than
its own prior output, so re-running does not progressively blur the art. The
full `build_video_actions.py` pipeline applies the same cleanup after extraction.
Updated preview: `docs/video-actions-once.gif` (single-pass, final holds for
comparison only, not extra XML durations).

## Verification and limits

65 unittest tests pass; all four packs pass validation. Tests cover exact key
pixels, integer vectors, down direction, unchanged cycle duration/displacement,
video endpoints/coverage, and finite playback followed by roaming. Asset import,
smoothing and XML generation are idempotent.

No live ShimeLinux/compositor test was available here. These checks do not prove
that all animation looks natural or that there are no interpolation artifacts.
Pickup, roaming and breeding settings are unchanged. No new action types or
extra Red image set were added in this smoothing pass.
